"""MANDATORY FIRST-RUN STEP: compare the enhancement tools on one of the user's own photos.

  system/.venv/bin/python system/scripts/tool_test.py "New photos/IMG_0123.HEIC"   (add --no-ai-extras to skip the AI add-ons)

Pick a photo from "New photos" — ideally an old print with a face. It is copied to
system/test photo/ (later runs without an argument reuse it). The script opens a comparison page:
drag the slider to compare, switch options with the buttons. Then save the choice:
  system/.venv/bin/python system/scripts/config.py enhancement <none|colors|colors+faces50|colors+faces100>
  system/.venv/bin/python system/scripts/config.py colorize bw       (optional, default off)
  system/.venv/bin/python system/scripts/config.py upscale 2x        (optional, default off)

Nothing is processed for real until the base enhancement is chosen (every script checks it).
All processing runs locally; the first run of the AI add-ons downloads their weights once
(Real-ESRGAN ~5 MB, colorization ~129 MB) from the official releases.
"""
import glob
import json
import os
import shutil
import subprocess
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import detect_photos  # noqa: E402
import enhance  # noqa: E402

given = [a for a in sys.argv[1:] if not a.startswith("--")]
if given:
    os.makedirs(common.TEST, exist_ok=True)
    for old in glob.glob(os.path.join(common.TEST, "*")):
        os.remove(old)
    src = os.path.join(common.TEST, os.path.basename(given[0]))
    shutil.copyfile(given[0] if os.path.isabs(given[0]) else os.path.join(common.ROOT, given[0]), src)
else:
    photos = sorted(p for p in glob.glob(os.path.join(common.TEST, "*")) if p.lower().endswith(common.IMAGE_EXT))
    if not photos:
        sys.exit('Name a test photo, e.g.: tool_test.py "New photos/IMG_0123.HEIC"')
    src = photos[0]
out = os.path.join(common.WORK, "_tool_test")
os.makedirs(os.path.join(out, "img"), exist_ok=True)

jpg = os.path.join(out, "snapshot.jpg")
subprocess.run(["sips", "-s", "format", "jpeg", src, "--out", jpg], check=True, capture_output=True)
img = cv2.imread(jpg)
corners, mode = detect_photos.detect(img)
crop = detect_photos.straighten(img, max(corners, key=cv2.contourArea)) if corners else img
print(f"Test photo: {os.path.basename(src)} ({mode}, {len(corners)} photo(s) found; testing on the largest)")

h, w = crop.shape[:2]
k = 1600 / max(h, w)
size = (int(w * k), int(h * k))


def save(image, key, dims=size):
    cv2.imwrite(os.path.join(out, "img", f"{key}.jpg"), cv2.resize(image, dims, interpolation=cv2.INTER_AREA),
                [cv2.IMWRITE_JPEG_QUALITY, 88])


def option(cmd, label, file, before="original", w_=None, h_=None, note=""):
    return {"cmd": cmd, "label": label, "file": file, "before": before,
            "w": w_ or size[0], "h": h_ or size[1], "note": note}


save(crop, "original")
colors, kind = enhance.restore_colors(crop)
colors = cv2.resize(colors, (w, h))
save(colors, "colors")
options = [option("enhancement none", "none — crop only", "original", note=common.ENHANCEMENTS["none"]),
           option("enhancement colors", f"colors ({kind})", "colors", note=common.ENHANCEMENTS["colors"])]
try:
    faces = enhance.Faces()
    print(f"Face restoration on: {faces.device}")
    for pct in (50, 100):
        result, n = faces.apply(colors, pct / 100)
        save(result, f"faces{pct}")
        options.append(option(f"enhancement colors+faces{pct}", f"colors + faces {pct} %" + ("" if n else " (no face found)"),
                              f"faces{pct}", note=common.ENHANCEMENTS[f"colors+faces{pct}"]))
except Exception as e:  # noqa: BLE001
    print(f"Face restoration not available ({e}) — run setup.sh.")

if "--no-ai-extras" not in sys.argv:
    import ai_models
    try:
        bw = enhance.is_black_and_white(crop)
        gray = colors if bw else cv2.cvtColor(cv2.cvtColor(colors, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
        if not bw:
            save(gray, "gray")
        save(ai_models.Colorizer().apply(gray), "colorized")
        options.append(option("colorize bw", "AI add-on: colorize", "colorized", "colors" if bw else "gray",
                              note="Black-and-white photos get AI-guessed colors (ECCV16). Skin, sky and grass are "
                                   "usually plausible; clothes and objects are a guess."
                                   + ("" if bw else " Your test photo is in color, so this demo uses a black-and-white copy.")))
    except Exception as e:  # noqa: BLE001
        print(f"Colorization not available: {e}")
    try:
        # upscaling only shows up when zoomed in: compare a detail, enlarged
        dh, dw = h // 3, w // 3
        detail = colors[(h - dh) // 2:(h + dh) // 2, (w - dw) // 2:(w + dw) // 2]
        up = ai_models.Upscaler().apply(detail, 2)
        dims = (1200, int(1200 * up.shape[0] / up.shape[1]))
        save(cv2.resize(detail, (dw * 2, dh * 2), interpolation=cv2.INTER_CUBIC), "detail_plain", dims)
        save(up, "detail_upscaled", dims)
        options.append(option("upscale 2x", "AI add-on: upscale 2× (detail)", "detail_upscaled", "detail_plain", *dims,
                              note="Real-ESRGAN, shown on an enlarged detail (left: plain enlargement). It sharpens, "
                                   "but invents fine texture that was never there — look at skin, hair and paper grain."))
    except Exception as e:  # noqa: BLE001
        print(f"Upscaling not available: {e}")

html = open(os.path.join(common.TEMPLATES, "compare.html"), encoding="utf-8").read()
html = html.replace("/*DATA*/", "const DATA = " + json.dumps({"options": options}, ensure_ascii=False) + ";")
page = os.path.join(out, "compare.html")
open(page, "w", encoding="utf-8").write(html)
subprocess.run(["open", page])
print(f"Comparison: {os.path.relpath(page, common.ROOT)}")
print(f"Options (save with {common.PY}/config.py <setting> <value>):")
for o in options:
    print(f"  {o['cmd']:30} {o['label']}")
print("The base enhancement is mandatory; the AI add-ons are optional and off by default.")
