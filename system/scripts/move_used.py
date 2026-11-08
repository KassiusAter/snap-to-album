"""Moves the originals of a finished album from New photos/ to system/used photos/,
so New photos/ only holds photos that are still waiting.

  system/.venv/bin/python system/scripts/move_used.py <album>

Only snapshots registered for this album (system/work/snapshots.json) are moved. Nothing is
ever deleted or overwritten: if system/used photos/ already holds a file with the same name
(a different photo with the same iPhone number), the moved one gets " (2)", " (3)" … added.
The scripts work with copies in system/work/, so albums can still be rebuilt.
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def free_name(folder, name):
    stem, ext = os.path.splitext(name)
    candidate, n = name, 1
    while os.path.exists(os.path.join(folder, candidate)):
        n += 1
        candidate = f"{stem} ({n}){ext}"
    return candidate


album = sys.argv[1]
os.makedirs(common.USED, exist_ok=True)
snapshots = common.load_snapshots()
moved = 0
for sid, entry in snapshots.items():
    src = os.path.join(common.NEW, entry["file"])
    if entry["album"] != album or entry.get("where") == "used" or not os.path.exists(src):
        continue
    target = free_name(common.USED, entry["file"])
    shutil.move(src, os.path.join(common.USED, target))
    if target != entry["file"]:
        print(f"  {entry['file']} → used photos/{target} (a file with that name was already there)")
    entry["file"] = target
    entry["where"] = "used"
    moved += 1
common.save_snapshots(snapshots)
print(f"Moved {moved} originals → system/used photos/")
