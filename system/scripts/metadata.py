"""Writes captions into photo metadata, so a photo keeps its caption outside the album too
(Apple Photos, Finder, other viewers).

  system/.venv/bin/python system/scripts/metadata.py <album>     (build_album.py and the captioning window call it)

Creates Albums/Photos with captions/<folder>/ with full-size final JPGs (copies — originals
and working files are never modified) and writes with exiftool:
  - caption → EXIF ImageDescription, IPTC Caption-Abstract, XMP dc:description
  - album name → keyword (IPTC Keywords, XMP dc:subject)
  - date, according to the "metadata_date" setting:
      year    (default) the year the photo shows, if known (caption → chapter → album title),
              as 1 January of that year — Photos then sorts by history (the exact day is unknown)
      capture when you took the snapshot (time source per "time_source")
      none    no date
  - a back side is saved next to its front as <front>_back.jpg
"""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

EXIFTOOL = shutil.which("exiftool") or "/opt/homebrew/bin/exiftool"


def folder(album):
    return os.path.join(common.CAPTIONED, album["folder"])


def tag_args(text, keyword, year, taken=None):
    """exiftool arguments for one photo."""
    args = [f"-EXIF:ImageDescription={text}", f"-IPTC:Caption-Abstract={text}", f"-XMP-dc:Description={text}",
            f"-IPTC:Keywords={keyword}", f"-XMP-dc:Subject={keyword}"]
    mode = common.load_config()["metadata_date"]
    if mode == "year" and year:
        date = f"{year}:01:01 12:00:00"
        args += [f"-EXIF:DateTimeOriginal={date}", f"-EXIF:CreateDate={date}", f"-XMP-photoshop:DateCreated={year}"]
    elif mode == "capture" and taken:
        date = taken.strftime("%Y:%m:%d %H:%M:%S")
        args += [f"-EXIF:DateTimeOriginal={date}", f"-EXIF:CreateDate={date}", f"-XMP-photoshop:DateCreated={taken.strftime('%Y-%m-%d')}"]
    else:
        args += ["-EXIF:DateTimeOriginal=", "-EXIF:CreateDate=", "-XMP-photoshop:DateCreated="]
    return args


COMMON_ARGS = ["-q", "-overwrite_original", "-charset", "iptc=UTF8", "-IPTC:CodedCharacterSet=UTF8"]


def write(path, text, keyword, year, taken=None):
    if os.path.exists(EXIFTOOL):
        subprocess.run([EXIFTOOL] + COMMON_ARGS + tag_args(text, keyword, year, taken) + [path], check=True)


def write_many(jobs):
    """jobs = [(path, args)] — ONE exiftool process for the whole album instead of one per photo
    (an album of 130 photos takes a second instead of half a minute)."""
    if not jobs or not os.path.exists(EXIFTOOL):
        return
    lines = []
    for path, args in jobs:
        lines += COMMON_ARGS + args + [path, "-execute"]
    subprocess.run([EXIFTOOL, "-@", "-"], input="\n".join(lines) + "\n", text=True, check=True, capture_output=True)


def export_photo(album, d, j, chapter, caps=None, jobs=None):
    """Copies the photo (and its back) into the export folder. With jobs given, the exiftool
    arguments are collected there instead of being run at once."""
    out = folder(album)
    os.makedirs(out, exist_ok=True)
    src = common.best_source(d, j)
    if not src:
        return None
    text = common.caption(album, j, caps)
    year, _ = common.year(text, chapter, album)
    keyword = os.path.splitext(album["output_file"])[0]
    path = os.path.join(out, f"{j}.jpg")
    shutil.copyfile(src, path)
    taken = common.capture_time(j.rsplit("_", 1)[0])
    todo = [(path, tag_args(text, keyword, year, taken))]
    back = common.back_of(album, d).get(j)
    if back and common.best_source(d, back):
        bp = os.path.join(out, f"{j}_back.jpg")
        shutil.copyfile(common.best_source(d, back), bp)
        todo.append((bp, tag_args(f"Back of photo: {text}" if text else "Back of photo", keyword, year, taken)))
    if jobs is None:
        write_many(todo)
    else:
        jobs += todo
    return path


def chapters_of(album, d):
    return {j: album["chapters"][c - 1] for j, c, _ in common.album_photos(album, d)[0]}


def export_album(name):
    album, d = common.load_album(name), common.album_dir(name)
    if album.get("source") == "photos":
        print("Metadata: photos come from the Photos app — no extra copies made")
        return
    caps = common.load_captions()
    chapters = chapters_of(album, d)
    jobs = []
    done = [export_photo(album, d, j, ch, caps, jobs) for j, ch in chapters.items()]
    write_many(jobs)
    # remove copies of photos that are no longer in this album (moved to another album) —
    # these are generated copies; originals and working files are never touched
    keep = {f"{j}.jpg" for j in chapters} | {f"{j}_back.jpg" for j in chapters}
    for f in os.listdir(folder(album)) if os.path.isdir(folder(album)) else []:
        if f.lower().endswith(".jpg") and f not in keep:
            os.remove(os.path.join(folder(album), f))
    note = "" if os.path.exists(EXIFTOOL) else " (exiftool missing — copies without captions)"
    print(f"Metadata: {sum(1 for x in done if x)} photos → {os.path.relpath(folder(album), common.ROOT)}/{note}")


def update(name, j):
    """After a caption change in the captioning window: rewrite one photo only."""
    album, d = common.load_album(name), common.album_dir(name)
    if album.get("source") == "photos":
        return None
    ch = chapters_of(album, d).get(j)
    if ch is not None:
        return export_photo(album, d, j, ch)


if __name__ == "__main__":
    export_album(sys.argv[1])
