"""Copies new snapshots into an album's working folder as full-size JPG + 1600 px previews.

  system/.venv/bin/python system/scripts/convert.py <album> [IMG_0001 IMG_0002 …]

Without names, takes every photo in New photos/. Uses macOS 'sips' (reads iPhone HEIC).
Originals stay untouched in New photos/ until the album is finished (move_used.py).
Every snapshot gets a unique id (normally its file name; IMG_0012-2 if another photo already
used that name) recorded in system/work/snapshots.json.
Prints the snapshots in the order they were taken, with the seconds between them —
handy for spotting back sides and close-ups photographed right after a photo.
"""
import glob
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

album = sys.argv[1]
names = sys.argv[2:]
d = common.album_dir(album)
for sub in ("jpg", "previews"):
    os.makedirs(os.path.join(d, sub), exist_ok=True)

files = sorted(p for p in glob.glob(os.path.join(common.NEW, "*")) if p.lower().endswith(common.IMAGE_EXT))
if names:
    files = [p for p in files if os.path.splitext(os.path.basename(p))[0] in names]
if not files:
    sys.exit("No photos found in New photos/.")

snapshots = common.load_snapshots()
stems = []
for p in files:
    owner = common.owner_of(os.path.basename(p), snapshots)
    if owner and snapshots[owner]["album"] != album:
        # still waiting in New photos for an album that is not finished yet — not ours
        print(f"  {os.path.basename(p)}: skipped, it belongs to the album “{snapshots[owner]['album']}”")
        continue
    stem = common.register_snapshot(p, album, snapshots)
    name = os.path.splitext(os.path.basename(p))[0]
    if stem != common.safe_id(name):
        print(f"  {os.path.basename(p)} → snapshot id {stem} (the name was already used by another photo)")
    elif stem != name:
        print(f"  {os.path.basename(p)} → snapshot id {stem} (special characters replaced)")
    full = os.path.join(d, "jpg", f"{stem}.jpg")
    subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "95", p, "--out", full],
                   check=True, capture_output=True)
    subprocess.run(["sips", "-Z", "1600", full, "--out", os.path.join(d, "previews", f"{stem}.jpg")],
                   check=True, capture_output=True)
    stems.append(stem)
common.save_snapshots(snapshots)

if not stems:
    sys.exit("No new photos for this album in New photos/.")
stems = common.shooting_order(stems)
print(f"Shooting order (time source: {common.load_config()['time_source']}):")
prev = None
for s in stems:
    t = common.capture_time(s)
    gap = f"+{(t - prev).total_seconds():.0f} s" if t and prev else ""
    print(f"{s}  {t.strftime('%Y-%m-%d %H:%M:%S') if t else '?':19}  {gap}")
    prev = t or prev
print(f"{len(stems)} snapshots → {os.path.relpath(d, common.ROOT)}/jpg and previews/")
