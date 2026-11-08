"""EXPERIMENTAL — captions back into the Apple Photos app.

For albums made from the Photos app (photos_album.py), every caption typed in the captioning window
is also written into the photo's own Caption field in the Photos app (the "Caption" shown in the
photo's Info) — on the original photo, no copy and no duplicate. It syncs through iCloud and makes
the photo searchable in Photos by its caption.

  system/.venv/bin/python system/scripts/photos_captions.py sync <album>    send all captions now

The captioning window does this automatically a moment after each Enter. An empty caption clears
the Caption field in Photos. Existing captions from Photos are pre-filled when the album is made,
so nothing is overwritten by accident.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def _quote(text):
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def read(uuids):
    """{uuid: caption} as currently stored in the Photos app."""
    if not uuids:
        return {}
    items = ", ".join(_quote(f"{u}/L0/001") for u in uuids)
    script = f'''tell application "Photos"
	set out to ""
	repeat with i in {{{items}}}
		try
			set d to description of media item id (contents of i)
			if d is missing value then set d to ""
			set out to out & (contents of i) & tab & d & linefeed
		end try
	end repeat
	return out
end tell'''
    res = subprocess.run(["osascript", "-"], input=script, capture_output=True, text=True, timeout=600)
    found = {}
    for line in res.stdout.splitlines():
        key, _, text = line.partition("\t")
        if key:
            found[key.split("/")[0]] = text
    return found


def write(captions):
    """Writes {uuid: caption} into the Photos app. Returns the number of photos updated."""
    if not captions:
        return 0
    lines = "\n".join(f'''	try
		set description of media item id {_quote(f"{u}/L0/001")} to {_quote(t)}
		set n to n + 1
	end try''' for u, t in captions.items())
    script = f'tell application "Photos"\n\tset n to 0\n{lines}\n\treturn n as text\nend tell'
    try:
        res = subprocess.run(["osascript", "-"], input=script, capture_output=True, text=True, timeout=600)
        return int(res.stdout.strip() or 0)
    except (subprocess.TimeoutExpired, ValueError):
        return 0


def for_album(name, ids_texts):
    """Maps {photo id: caption} of a Photos-made album to {uuid: caption}."""
    a = common.load_album(name)
    uuids = a.get("photos_ids", {})
    return {uuids[j]: t for j, t in ids_texts.items() if j in uuids}


def sync(name):
    a, caps = common.load_album(name), common.load_captions()
    if a.get("source") != "photos":
        sys.exit("This album was not made from the Photos app.")
    texts = {j: common.caption(a, j, caps) for j in a.get("photos_ids", {})}
    n = write(for_album(name, texts))
    print(f"Captions written into the Photos app: {n} of {len(texts)} photos")


if __name__ == "__main__":
    if sys.argv[1:2] == ["sync"] and len(sys.argv) > 2:
        sync(sys.argv[2])
    else:
        sys.exit(__doc__)
