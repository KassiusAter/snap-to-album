"""EXPERIMENTAL — a Snap to Album HTML album from a trip in your Apple Photos library.

  system/.venv/bin/python system/scripts/photos_album.py <trip number> "<album title>" [--count 50]

(trip numbers come from `photos_trips.py list`)

1. Picks the best photos of the trip:
   - Apple's own aesthetic score, favorites count extra
   - near-duplicates (photos taken within 90 seconds of each other) → only the best one
   - spread over all days of the trip (each day gets a share, busier days a bit more)
   - only your own photos (no other people's shared albums, no hidden burst frames, no videos)
2. Lets Photos export them (it downloads originals from iCloud if needed) into a temporary folder,
   keeps a resized working copy (2400 px) for rebuilding and deletes the raw exports.
3. Builds the album: one chapter per day, titled with Apple's place names; no cropping or color
   restoration (digital photos do not need it). Then creates the captioning launcher.

Nothing in the Photos library is changed. The result is a normal Snap to Album: Albums/<file>.html
plus "<file> – add captions.command".
"""
import collections
import datetime as dt
import json
import math
import os
import shutil
import subprocess
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import photos_trips as pt  # noqa: E402

DUPLICATE_GAP = 90      # seconds
WORKING_SIZE = 2400     # px, longer side of the kept working copy


def pick(rows, count):
    """Best photos, without near-duplicates, spread over the days."""
    # near-duplicates: photos within DUPLICATE_GAP of the FIRST photo of a group (so a long shooting
    # session is split into many short groups, not merged into one)
    clusters = []
    for r in rows:
        if clusters and r["t"] - clusters[-1][0]["t"] <= DUPLICATE_GAP:
            clusters[-1].append(r)
        else:
            clusters.append([r])
    best = [max(c, key=lambda r: r["score"]) for c in clusters]
    by_day = collections.defaultdict(list)
    for r in best:
        by_day[r["day"]].append(r)
    for v in by_day.values():
        v.sort(key=lambda r: r["score"], reverse=True)
    weights = {d: math.sqrt(len(v)) for d, v in by_day.items()}
    total = sum(weights.values())
    quota = {d: max(1, round(count * weights[d] / total)) for d in by_day}
    chosen = [r for d, v in by_day.items() for r in v[:quota[d]]]
    # days with fewer photos than their share leave places free — fill them with the best of the rest
    rest = sorted((r for d, v in by_day.items() for r in v[quota[d]:]), key=lambda r: r["score"], reverse=True)
    chosen += rest[:max(0, count - len(chosen))]
    if len(chosen) > count:   # rounding: drop the weakest, but keep at least one photo per day
        keep, seen = [], set()
        for r in sorted(chosen, key=lambda r: r["score"], reverse=True):
            if len(keep) < count or r["day"] not in seen:
                keep.append(r)
            seen.add(r["day"])
        chosen = keep
    return sorted(chosen, key=lambda r: r["t"])


def export(uuids, folder):
    """Photos exports each photo into its own subfolder (file names can repeat). A photo that cannot
    be exported (not downloadable from iCloud, deleted meanwhile) is skipped, not fatal."""
    os.makedirs(folder, exist_ok=True)
    lines = []
    for u in uuids:
        sub = os.path.join(folder, u)
        os.makedirs(sub, exist_ok=True)
        lines.append(f'''	try
		export {{media item id "{u}/L0/001"}} to (POSIX file "{sub}" as alias)
	end try''')
    script = 'tell application "Photos"\n' + "\n".join(lines) + '\nend tell'
    try:
        subprocess.run(["osascript", "-"], input=script, capture_output=True, text=True, timeout=7200)
    except subprocess.TimeoutExpired:
        print("Photos took very long — continuing with what was exported.")


def main(number, title, count):
    cache = json.load(open(pt.CACHE)) if os.path.exists(pt.CACHE) else {"trips": [], "home": None}
    trips, home = cache["trips"], cache.get("home")
    trip = next((t for t in trips if t["number"] == number), None)
    if not trip:
        sys.exit("Run 'photos_trips.py list' first and use a trip number from it.")
    db = pt.library_db()
    rows = []
    for r in pt.load(db):
        # own photos only: no videos (kind 1), no other people's shared albums, no hidden burst frames
        if trip["t0"] <= r[1] <= trip["t1"] and not r[8] and not r[9] and r[11] == 0:
            t = pt.when(r[1], r[10])   # local time where the photo was taken
            near_home = bool(home) and pt.has_gps(r[2], r[3]) and pt.km((r[2], r[3]), home) < pt.AWAY_KM
            rows.append({"uuid": r[0], "t": r[1], "time": t, "day": t.date(),
                         "place": "" if near_home else r[6],   # home is not a chapter title
                         "score": r[4] + (0.3 if r[5] else 0)})
    if not rows:
        sys.exit("No photos of your own in this trip.")
    chosen = pick(rows, count)
    print(f"Trip #{number}: {len(rows)} photos → {len(chosen)} picked over {len({r['day'] for r in chosen})} days")

    name = common.safe_id(title).lower()
    d = common.album_dir(name)
    if os.path.exists(os.path.join(d, "album.json")):
        sys.exit(f"An album '{name}' already exists in system/work/.")
    for sub in ("jpg", "crops"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    tmp = os.path.join(d, "_export")
    print("Exporting from Photos (downloads from iCloud if needed)…")
    try:
        export([r["uuid"] for r in chosen], tmp)
        used = set()
        for r in chosen:
            sub = os.path.join(tmp, r["uuid"])
            files = [f for f in os.listdir(sub) if not f.startswith(".")] if os.path.isdir(sub) else []
            img = cv2.imread(os.path.join(sub, files[0])) if files else None
            if img is None:
                print(f"  {r['time']:%Y-%m-%d %H:%M}: could not be exported, skipped")
                continue
            sid = "P" + r["time"].strftime("%Y%m%d-%H%M%S")
            while sid in used:
                sid += "b"
            used.add(sid)
            r["id"] = f"{sid}_1"
            h, w = img.shape[:2]
            k = min(1.0, WORKING_SIZE / max(h, w))
            if k < 1:
                img = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
            cv2.imwrite(os.path.join(d, "crops", f"{r['id']}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)   # raw full-size exports are never kept
    chosen = [r for r in chosen if "id" in r]
    if not chosen:
        shutil.rmtree(d, ignore_errors=True)
        sys.exit("No photo could be exported from Photos (are you online for iCloud downloads?). Nothing was created.")

    chapters = []
    by_day = collections.OrderedDict()
    for r in chosen:
        by_day.setdefault(r["day"], []).append(r)
    for i, (day, items) in enumerate(by_day.items(), 1):
        places = [p for p, _ in collections.Counter(r["place"] for r in items if r["place"]).most_common(2)]
        top = sorted(items, key=lambda r: r["score"], reverse=True)[:2]
        chapters.append({"group": f"Day {i}", "title": " · ".join(places) or f"Day {i}",
                         "date": f"{day.day}. {day.month}. {day.year}",
                         "featured": [r["id"] for r in sorted(top, key=lambda r: r["t"])],
                         "grid": [r["id"] for r in items if r not in top]})
    first, last = chosen[0]["day"], chosen[-1]["day"]
    span = f"{first.day}. {first.month}. – {last.day}. {last.month}. {last.year}"
    album = {"title": title, "subtitle": span, "source": "photos", "lang": "en",
             "intro": f"{len(chosen)} photos picked from {len(rows)}.",
             "caption_label": "Place",
             "output_file": f"{title}.html" if str(first.year) in title else f"{first.year} {title}.html",
             "folder": name,
             "chapters": chapters}
    json.dump(album, open(os.path.join(d, "album.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    import build_album
    build_album.build(name)
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "make_launcher.py"), name], check=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 2:
        sys.exit(__doc__)
    opts = dict(zip(a[2::2], a[3::2]))
    main(int(a[0].lstrip("#")), a[1], int(opts.get("--count", 50)))
