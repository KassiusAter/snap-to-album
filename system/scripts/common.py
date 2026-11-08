"""Shared paths and helpers used by all scripts.

What the user sees (project folder):
  RUN Snap to Album.command   double-click: starts Claude with "create a photo album"
  New photos/             drop new iPhone photos here (HEIC/JPG/PNG)
  Albums/                 finished albums (one offline HTML file each), their
                          "<album> – add captions.command" launchers and
                          "Photos with captions/" (JPGs with captions in their metadata)
Everything technical lives in system/:
  system/scripts, templates   this code
  system/.venv, models        Python environment and model weights (created by setup.sh)
  system/config.json          your settings
  system/work/<album>/        working files per album, captions.json, inventory.db
  system/folder_version/      albums as folders (used by the captioning window)
  system/used photos/         originals that are already in an album
  system/test photo/          the photo used for the first-run tool choice

Album working folder system/work/<album>/:
  album.json            title, chapters, captions … (written by Claude, approved by you)
  jpg/ previews/        full-size JPG copies and 1600 px previews of the snapshots
  crops/                photos cut out of the snapshots: <snapshot>_<n>.jpg
  check/                snapshots with numbered boxes to verify the crops
  enhanced/ final/      after color correction / after all further steps
  manual_corners.json   corrections where automatic detection fails
  rotate.json           rotation of individual crops
  backs.json            confirmed back-side pairs {"<back id>": "<front id>"}
"""
import glob
import json
import os
import subprocess
import sys
from datetime import datetime
from functools import lru_cache

SYSTEM = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(SYSTEM)
NEW = os.path.join(ROOT, "New photos")
ALBUMS = os.path.join(ROOT, "Albums")
CAPTIONED = os.path.join(ALBUMS, "Photos with captions")
WORK = os.path.join(SYSTEM, "work")
FOLDERS = os.path.join(SYSTEM, "folder_version")
USED = os.path.join(SYSTEM, "used photos")
TEST = os.path.join(SYSTEM, "test photo")
MODELS = os.path.join(SYSTEM, "models")
TEMPLATES = os.path.join(SYSTEM, "templates")
CONFIG = os.path.join(SYSTEM, "config.json")
CAPTIONS = os.path.join(WORK, "captions.json")
SNAPSHOTS = os.path.join(WORK, "snapshots.json")   # snapshot id → original file name and album
PY = "system/.venv/bin/python system/scripts"   # how commands are shown to the user/Claude
IMAGE_EXT = (".heic", ".jpg", ".jpeg", ".png", ".tif", ".tiff")

# Enhancement options offered in the first-run step (tool_test.py).
ENHANCEMENTS = {
    "none": "Crop and straighten only — no changes to the image",
    "colors": "Crop + automatic color/contrast restoration (OpenCV)",
    "colors+faces50": "Crop + colors + gentle face restoration (GFPGAN mixed 50 % with the original)",
    "colors+faces100": "Crop + colors + full face restoration (GFPGAN 100 %)",
}

# All settings in config.json: allowed values (None = a number) and what they mean.
# "enhancement" is mandatory (first-run step); the rest have defaults.
SETTINGS = {
    "enhancement": (list(ENHANCEMENTS), None, "base enhancement — chosen on your test photo"),
    "colorize": (["off", "bw"], "off",
                 "AI colorization of black-and-white photos (ECCV16 model; colors are a guess)"),
    "upscale": (["off", "2x", "4x"], "off",
                "AI upscaling (Real-ESRGAN; adds invented fine detail)"),
    "view_photos": (["yes", "no"], None,
                    "may Claude open photo previews (they are then sent to the model provider)"),
    "time_source": (["auto", "exif", "file", "name"], "auto",
                    "how to tell when each snapshot was taken: exif = camera/iPhone time, "
                    "file = file date (scanners, edited files), name = file-name order only, "
                    "auto = exif, else file date, else name"),
    "back_max_gap": (None, 60,
                     "max. seconds between a photo and its back side; 0 = ignore time, use order only"),
    "metadata_date": (["year", "capture", "none"], "year",
                      "date written into the photos with captions: year = the year the photo shows "
                      "(from caption/chapter, so Photos sorts by history), capture = when you took "
                      "the snapshot, none = no date"),
}


# ---------- config ----------

def load_config():
    cfg = json.load(open(CONFIG, encoding="utf-8")) if os.path.exists(CONFIG) else {}
    for key, (_, default, _) in SETTINGS.items():
        if default is not None:
            cfg.setdefault(key, default)
    return cfg


def save_config(cfg):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def require_config():
    """Stops every processing script until the mandatory first-run step is done."""
    cfg = load_config()
    if cfg.get("enhancement") not in ENHANCEMENTS:
        sys.exit("First-run step missing: choose how photos are enhanced, on a test photo.\n"
                 f"  1. {PY}/tool_test.py \"New photos/<one photo with a face>\"\n"
                 f"  2. {PY}/config.py enhancement <option>")
    return cfg


# ---------- albums ----------

def album_dir(name):
    return os.path.join(WORK, name)


def album_names():
    return sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(WORK, "*", "album.json")))


def load_album(name):
    a = json.load(open(os.path.join(album_dir(name), "album.json"), encoding="utf-8"))
    a.setdefault("chapters", [])
    a.setdefault("captions", {})
    a.setdefault("clippings", [])
    a.setdefault("use_closeup", {})
    a.setdefault("folder", name)
    a.setdefault("output_file", f"{a.get('title', name)}.html")
    # file and folder names only — never a path that could point outside Albums/ or system/
    a["folder"] = os.path.basename(str(a["folder"]).replace("\\", "/")).strip(". ") or name
    a["output_file"] = os.path.basename(str(a["output_file"]).replace("\\", "/")).strip() or f"{name}.html"
    if not a["output_file"].lower().endswith(".html"):
        a["output_file"] += ".html"
    return a


def all_album_dirs(first=None):
    dirs = [os.path.dirname(p) for p in glob.glob(os.path.join(WORK, "*", "jpg"))]
    return ([first] if first else []) + sorted(x for x in dirs if x != first)


def photo_dir(d, j):
    """Album folder that holds photo j — its own album first, then any other album
    (photos can be moved between albums just by listing them in another album.json)."""
    for x in all_album_dirs(d):
        if os.path.exists(os.path.join(x, "crops", f"{j}.jpg")):
            return x
    return None


def snapshot_dir(d, snapshot):
    for x in all_album_dirs(d):
        if os.path.exists(os.path.join(x, "jpg", f"{snapshot}.jpg")):
            return x
    return None


def crops_of(folder, snapshot):
    """Crop files of exactly this snapshot (<snapshot>_<number>.jpg) — not of a snapshot whose
    name merely starts the same ('page' must not pick up 'page_2_1.jpg')."""
    import re
    rx = re.compile(re.escape(snapshot) + r"_(\d+)\.jpg$")
    found = []
    for p in glob.glob(os.path.join(folder, glob.escape(snapshot) + "_*.jpg")):
        m = rx.match(os.path.basename(p))
        if m:
            found.append((int(m.group(1)), p))
    return [p for _, p in sorted(found)]


def page_photos(d, snapshot):
    src = snapshot_dir(d, snapshot) or d
    return [os.path.splitext(os.path.basename(p))[0] for p in crops_of(os.path.join(src, "crops"), snapshot)]


def clippings(album, d):
    """Clippings: from album.json and from clippings.json (written while sorting the snapshots,
    before enhancement runs) — they only get gentle processing."""
    p = os.path.join(d, "clippings.json")
    extra = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []
    return set((album or {}).get("clippings", [])) | set(extra)


def backs(d):
    p = os.path.join(d, "backs.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def back_of(album, d):
    """{front as shown in the album: back} — if the front was replaced by a close-up, the back
    belongs to the close-up."""
    sub = (album or {}).get("use_closeup", {})
    return {sub.get(front, front): back for back, front in backs(d).items()}


def album_photos(album, d):
    """Photos in album order: [(id, chapter_number, chapter_title)] and the list of pages.
    Close-ups replace their page crop ("use_closeup"); back sides are attached to their
    front, not listed as separate photos."""
    b, sub = backs(d), album["use_closeup"]
    photos, pages, seen = [], [], set()
    for i, ch in enumerate(album["chapters"], 1):
        ids = list(ch.get("featured", []))
        for p in ch.get("pages", []):
            pages.append(p)
            ids += page_photos(d, p)
        ids += ch.get("grid", [])
        for j in ids:
            j = sub.get(j, j)
            if j not in seen and j not in b:
                seen.add(j)
                photos.append((j, i, ch["title"]))
    return photos, pages


def best_source(d, j):
    """Most processed version available: final → enhanced → crops (in whichever album holds it)."""
    x = photo_dir(d, j)
    for sub in ("final", "enhanced", "crops"):
        p = os.path.join(x or d, sub, f"{j}.jpg")
        if os.path.exists(p):
            return p
    return None


def crop_source(d, j):
    x = photo_dir(d, j)
    return os.path.join(x, "crops", f"{j}.jpg") if x else None


# ---------- captions and years ----------

def load_captions():
    return json.load(open(CAPTIONS, encoding="utf-8")) if os.path.exists(CAPTIONS) else {}


def caption(album, j, caps=None):
    """A caption typed in the captioning window wins — also an empty one, which means the
    family deleted the caption on purpose."""
    caps = load_captions() if caps is None else caps
    return caps[j] if j in caps else album["captions"].get(j, "")


def year(text, chapter=None, album=None):
    """Year of a photo: first year in its caption (years >= the current year are skipped —
    captions are written today, "still there today (2026)" is not the photo's year),
    else the chapter's year/date, else the only year in the album title."""
    import re
    rx = re.compile(r"(?<!\d)(1[89]\d\d|20[0-4]\d)(?!\d)")   # also "1950s", "1960er", "1975:"
    for y in rx.findall(text or ""):
        if int(y) < datetime.now().year:
            return int(y), "caption"
    if chapter:
        if isinstance(chapter.get("group"), int):
            return chapter["group"], "chapter"
        m = rx.search(str(chapter.get("date", "")))
        if m:
            return int(m.group(1)), "chapter"
    if album:
        ys = set(rx.findall(f"{album.get('title', '')} {album.get('subtitle', '')}"))
        if len(ys) == 1:
            return int(ys.pop()), "album"
    return None, None


# ---------- originals ----------

def load_snapshots():
    return json.load(open(SNAPSHOTS, encoding="utf-8")) if os.path.exists(SNAPSHOTS) else {}


def save_snapshots(m):
    os.makedirs(WORK, exist_ok=True)
    tmp = SNAPSHOTS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SNAPSHOTS)


def safe_id(name):
    """File name → id that is safe in web pages and URLs: letters, digits, '.', '_' and '-'
    only ('Grand-mère & Père #2' → 'Grand-mere-Pere-2'). iPhone names stay as they are."""
    import re
    import unicodedata
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9._-]+", "-", ascii_name).strip("-") or "photo"


def owner_of(base, m):
    """Snapshot id of a file that is still waiting in New photos, or None."""
    for sid, e in m.items():
        if e["file"] == base and e.get("where", "new") == "new":
            return sid
    return None


def register_snapshot(original, album, m):
    """Unique snapshot id for an original file in New photos. Usually its file name (IMG_0012);
    if that id is already taken by a different photo — iPhone numbering restarts after 9999, a
    second phone, IMG_0012.HEIC next to an edited IMG_0012.JPG, or the old IMG_0012 of a finished
    album that has already been moved to used photos — it becomes IMG_0012-2, -3, …"""
    base = os.path.basename(original)
    stem = safe_id(os.path.splitext(base)[0])
    sid, n = stem, 1
    while sid in m and not (m[sid]["file"] == base and m[sid]["album"] == album
                            and m[sid].get("where", "new") == "new"):
        n += 1
        sid = f"{stem}-{n}"
    m[sid] = {"file": base, "album": album, "where": "new"}
    return sid


def find_original(snapshot):
    """Path of a snapshot's original. Registered snapshots are looked up exactly where they are
    recorded (New photos or used photos), so two different photos with the same file name — one
    already used, one new — are never confused."""
    entry = load_snapshots().get(snapshot)
    if entry:
        folder = USED if entry.get("where") == "used" else NEW
        p = os.path.join(folder, entry["file"])
        return p if os.path.exists(p) else None
    for folder in (NEW, USED):
        for p in glob.glob(os.path.join(folder, glob.escape(snapshot) + ".*")):
            if p.lower().endswith(IMAGE_EXT):
                return p
    return None


@lru_cache(maxsize=1)
def _exif_times():
    """Capture times of all originals from EXIF, read with ONE exiftool call.
    (File dates are useless: copying a photo gives it a new date.)"""
    import shutil
    files = [p for folder in (NEW, USED) for p in glob.glob(os.path.join(folder, "*")) if p.lower().endswith(IMAGE_EXT)]
    tool = shutil.which("exiftool") or "/opt/homebrew/bin/exiftool"
    if not files or not os.path.exists(tool):
        return {}
    out = subprocess.run([tool, "-json", "-q", "-SubSecDateTimeOriginal", "-DateTimeOriginal", "-OffsetTimeOriginal"] + files,
                         capture_output=True, text=True).stdout
    times = {}
    for item in json.loads(out or "[]"):
        stem = os.path.abspath(item["SourceFile"])   # full path: same names in two folders stay apart
        for key, fmt in (("SubSecDateTimeOriginal", "%Y:%m:%d %H:%M:%S.%f%z"), ("SubSecDateTimeOriginal", "%Y:%m:%d %H:%M:%S.%f"),
                         ("DateTimeOriginal", "%Y:%m:%d %H:%M:%S")):
            try:
                times[stem] = datetime.strptime(str(item.get(key, "")), fmt).astimezone()
                break
            except ValueError:
                continue
    return times


def _file_time(snapshot):
    p = find_original(snapshot)
    if not p:
        return None
    st = os.stat(p)
    return datetime.fromtimestamp(getattr(st, "st_birthtime", st.st_mtime)).astimezone()


@lru_cache(maxsize=None)
def capture_time(snapshot):
    """When the snapshot was taken, according to the "time_source" setting:
    exif (camera/iPhone time), file (file date — scanners, files without EXIF),
    name (no time, file-name order only), auto (exif → file date). None if unknown."""
    source = load_config()["time_source"]
    if source == "name":
        return None
    if source in ("exif", "auto"):
        orig = find_original(snapshot)
        t = _exif_times().get(os.path.abspath(orig)) if orig else None
        if t or source == "exif":
            return t
    return _file_time(snapshot)


def shooting_order(snapshots):
    """Snapshots in the order they were taken (time per "time_source"; file name breaks ties
    and orders snapshots without a time)."""
    return sorted(snapshots, key=lambda s: (capture_time(s).timestamp() if capture_time(s) else float("inf"), s))


# ---------- compute device ----------

def device():
    """Fastest local device for PyTorch: NVIDIA GPU (CUDA) → Apple GPU (MPS) → CPU."""
    import torch
    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")
