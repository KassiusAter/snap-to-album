"""Finds the photos on each snapshot, straightens them and saves them as crops/<snapshot>_<n>.jpg
(numbered top-to-bottom, left-to-right). No color changes here — only cropping.

  system/.venv/bin/python system/scripts/detect_photos.py <album> [IMG_0001 …]

Automatic mode per snapshot:
  - album page (dark page, several light rectangles) → every photo on the page separately
  - single photo (on a table / dark background) → the largest light quadrilateral
For verification it writes check/<snapshot>.jpg (numbered boxes) and check/_overview.jpg.

Corrections in system/work/<album>/manual_corners.json, coordinates in the 1600 px PREVIEW:
  {"IMG_0001": "whole",                      use the whole snapshot (already cropped)
   "IMG_0002": "single",                     force single-photo detection
   "IMG_0003": [[[x,y],[x,y],[x,y],[x,y]], …]}  explicit corners of each photo

Rotation of individual crops in system/work/<album>/rotate.json (degrees clockwise):
  {"IMG_0004_1": 90, "IMG_0005_1": 180}
"""
import glob
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def order_corners(pts):
    """top-left, top-right, bottom-right, bottom-left"""
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], dtype=np.float32)


def straighten(img, corners):
    tl, tr, br, bl = corners
    w = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    h = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
    return cv2.warpPerspective(img, cv2.getPerspectiveTransform(corners, dst), (w, h), flags=cv2.INTER_CUBIC)


def _quad(hull):
    perimeter = cv2.arcLength(hull, True)
    for eps in (0.02, 0.03, 0.04, 0.06):
        approx = cv2.approxPolyDP(hull, eps * perimeter, True)
        if len(approx) == 4:
            return approx.reshape(4, 2).astype(np.float32)
    return cv2.boxPoints(cv2.minAreaRect(hull)).astype(np.float32)


def page_rectangles(img):
    """Light rectangles (photos with white borders, clippings) on a dark album page."""
    h, w = img.shape[:2]
    k = 1200 / max(h, w)
    small = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    L = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2LAB)[:, :, 0], (5, 5), 0)
    mask = cv2.threshold(L, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    # photos on a page often touch — separate them with a narrow opening first
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    area = small.shape[0] * small.shape[1]
    found = []
    for c in contours:
        hull = cv2.convexHull(c)
        if not 0.02 * area < cv2.contourArea(hull) < 0.9 * area:
            continue
        rect = cv2.minAreaRect(hull)
        if cv2.contourArea(hull) < 0.85 * rect[1][0] * rect[1][1]:
            continue  # handwriting, page edge
        found.append(order_corners(cv2.boxPoints(rect).astype(np.float32) / k))
    # rows: photos whose top edges differ by less than a tenth of the page
    found.sort(key=lambda r: r[0][1])
    rows, last = [], None
    for r in found:
        if last is None or r[0][1] - last > 0.1 * h:
            rows.append([])
        rows[-1].append(r)
        last = r[0][1]
    return [r for row in rows for r in sorted(row, key=lambda r: r[0][0])]


def dark_background(img):
    h, w = img.shape[:2]
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    p = int(0.03 * min(h, w))
    band = np.concatenate([g[:p].ravel(), g[-p:].ravel(), g[:, :p].ravel(), g[:, -p:].ravel()])
    return np.median(band) < 90


def single_photo_dark(img):
    """Largest light quadrilateral on a darker or textured background."""
    h, w = img.shape[:2]
    k = 1000 / max(h, w)
    small = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    L = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2LAB)[:, :, 0], (9, 9), 0)
    area = small.shape[0] * small.shape[1]
    masks = [cv2.threshold(L, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
             cv2.dilate(cv2.Canny(L, 30, 90), np.ones((5, 5), np.uint8), iterations=2)]
    best, best_area = None, 0
    for m in masks:
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
        for c in cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
            if not 0.15 * area < cv2.contourArea(c) < 0.97 * area:
                continue
            q = _quad(cv2.convexHull(c))
            a = cv2.contourArea(q)
            if a > best_area:
                best, best_area = q, a
    return None if best is None else order_corners(best / k)


def single_photo_light(img):
    """Photo on a light textured table: GrabCut separates it by color and texture."""
    h, w = img.shape[:2]
    k = 800 / max(h, w)
    small = cv2.bilateralFilter(cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA), 9, 60, 60)
    sh, sw = small.shape[:2]
    mask = np.zeros((sh, sw), np.uint8)
    m = int(0.02 * max(sh, sw))
    bg, fg = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(small, mask, (m, m, sw - 2 * m, sh - 2 * m), bg, fg, 6, cv2.GC_INIT_WITH_RECT)
    fore = np.where((mask == 1) | (mask == 3), 255, 0).astype(np.uint8)
    fore = cv2.morphologyEx(fore, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    fore = cv2.morphologyEx(fore, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    contours, _ = cv2.findContours(fore, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    c = max(contours, key=cv2.contourArea)
    if cv2.contourArea(c) < 0.15 * sh * sw:
        return None
    return order_corners(_quad(cv2.convexHull(c)) / k)


def detect(img, mode=None):
    """Returns a list of corner sets (one per photo) and the mode that was used."""
    if mode != "single":
        rects = page_rectangles(img)
        if len(rects) >= 2 or mode == "page":
            return rects, "page"
    c = single_photo_dark(img) if dark_background(img) else single_photo_light(img)
    return ([c] if c is not None else []), "single"


ROTATE = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}


def process(d, snapshot, manual, rotate=None):
    img = cv2.imread(os.path.join(d, "jpg", f"{snapshot}.jpg"))
    if img is None:
        print(f"{snapshot}: cannot be read as an image — skipped")
        return
    h, w = img.shape[:2]
    m = manual.get(snapshot)
    if m == "whole":
        corners, mode = [np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], np.float32)], "whole"
    elif isinstance(m, list):
        scale = max(h, w) / 1600
        corners, mode = [order_corners(np.array(r, np.float32) * scale) for r in m], "manual"
    else:
        corners, mode = detect(img, m)
    # remove this snapshot's old crops and their processed versions (they no longer match);
    # the build processes the new crops again
    for sub, ext in (("crops", "jpg"), ("enhanced", "jpg"), ("enhanced", "cfg"), ("final", "jpg")):
        for old in common.crops_of(os.path.join(d, sub), snapshot, ext):
            os.remove(old)
    k = 1400 / max(h, w)
    view = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    for i, r in enumerate(corners, 1):
        crop = straighten(img, r)
        turn = (rotate or {}).get(f"{snapshot}_{i}")
        if turn in ROTATE:
            crop = cv2.rotate(crop, ROTATE[turn])
        cv2.imwrite(os.path.join(d, "crops", f"{snapshot}_{i}.jpg"), crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
        cv2.polylines(view, [(r * k).astype(np.int32)], True, (0, 0, 255), 4)
        cv2.putText(view, str(i), tuple((r.mean(axis=0) * k).astype(int)), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 255), 8)
    cv2.putText(view, snapshot, (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 200, 255), 5)
    cv2.imwrite(os.path.join(d, "check", f"{snapshot}.jpg"), view, [cv2.IMWRITE_JPEG_QUALITY, 80])
    print(f"{snapshot}: {len(corners)} photo(s) [{mode}]" + ("  ← NOTHING FOUND, check it" if not corners else ""))


def overview(d):
    """All check images on one contact sheet (fewer images to look at)."""
    tiles = []
    for p in sorted(glob.glob(os.path.join(d, "check", "[!_]*.jpg"))):
        t = cv2.imread(p)
        k = 360 / max(t.shape[:2])
        tiles.append((p, cv2.resize(t, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)))
    if not tiles:
        return
    cols = 5
    sheet = np.full((((len(tiles) + cols - 1) // cols) * 370, cols * 370, 3), 40, np.uint8)
    for n, (_, t) in enumerate(tiles):
        y, x = (n // cols) * 370 + 5, (n % cols) * 370 + 5
        sheet[y:y + t.shape[0], x:x + t.shape[1]] = t
    cv2.imwrite(os.path.join(d, "check", "_overview.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 80])


if __name__ == "__main__":
    common.require_config()
    d = common.album_dir(sys.argv[1])
    for sub in ("crops", "check"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    mf = os.path.join(d, "manual_corners.json")
    manual = json.load(open(mf, encoding="utf-8")) if os.path.exists(mf) else {}
    rf = os.path.join(d, "rotate.json")
    rotate = {k: int(v) for k, v in json.load(open(rf, encoding="utf-8")).items()} if os.path.exists(rf) else {}
    names = sys.argv[2:] or [os.path.splitext(os.path.basename(p))[0] for p in sorted(glob.glob(os.path.join(d, "jpg", "*.jpg")))]
    for s in names:
        process(d, s, manual, rotate)
    overview(d)
    print(f"Check: {os.path.relpath(os.path.join(d, 'check', '_overview.jpg'), common.ROOT)}")
