"""Inventory of all snapshots and photos in all albums → system/work/inventory.db (SQLite, local only).

The inventory is always rebuilt from the current state (album.json files, captions.json,
backs.json, photo folders), so it can never drift from reality. The captioning window also
updates a photo's caption and year right after each Enter.

Tables:
  albums    name, title, output_file, folder, photo_count
  snapshots file (snapshot id, e.g. IMG_0001 or IMG_0001-2), path of the original, taken, album
  photos    id (IMG_0001_1) + album (a photo may appear in more than one album), snapshot, chapter, position, kind (photo / back / clipping),
            front (for a back side), back (for a front), caption, caption_source (album / captioning),
            year, year_source (caption / chapter / album), jpg_with_metadata
View uncaptioned = photos without a caption.

  system/.venv/bin/python system/scripts/inventory.py        rebuild and print a short summary
  sqlite3 system/work/inventory.db "select id, year, caption from photos where album='summer_1994'"
"""
import glob
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import metadata  # noqa: E402

DB = os.path.join(common.WORK, "inventory.db")
SCHEMA = """
CREATE TABLE albums (name TEXT PRIMARY KEY, title TEXT, output_file TEXT, folder TEXT, photo_count INTEGER);
CREATE TABLE snapshots (file TEXT PRIMARY KEY, path TEXT, taken TEXT, album TEXT);
CREATE TABLE photos (id TEXT, album TEXT, snapshot TEXT, chapter TEXT, position INTEGER,
  kind TEXT, front TEXT, back TEXT, caption TEXT, caption_source TEXT, year INTEGER, year_source TEXT,
  jpg_with_metadata TEXT, PRIMARY KEY (album, id));
CREATE VIEW uncaptioned AS SELECT album, id, chapter FROM photos WHERE kind != 'back' AND (caption IS NULL OR caption = '');
"""


def build():
    tmp = DB + ".new"
    if os.path.exists(tmp):
        os.remove(tmp)
    os.makedirs(common.WORK, exist_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript(SCHEMA)
    caps = common.load_captions()
    snapshot_album = {}
    for name in common.album_names():
        a, d = common.load_album(name), common.album_dir(name)
        photos, _ = common.album_photos(a, d)
        backs = common.backs(d)
        back_of = common.back_of(a, d)
        exp = metadata.folder(a)
        clips = common.clippings(a, d)
        rows = []
        for pos, (j, c, chapter) in enumerate(photos, 1):
            text = common.caption(a, j, caps)
            year, ysrc = common.year(text, a["chapters"][c - 1], a)
            jpg = os.path.join(exp, f"{j}.jpg")
            rows.append((j, name, j.rsplit("_", 1)[0], chapter, pos,
                         "clipping" if j in clips else "photo", None, back_of.get(j), text,
                         ("captioning" if j in caps else "album") if text else None, year, ysrc,
                         os.path.relpath(jpg, common.ROOT) if os.path.exists(jpg) else None))
        for b, f in backs.items():
            rows.append((b, name, b.rsplit("_", 1)[0], None, None, "back", f, None,
                         common.caption(a, b, caps), None, None, None, None))
        db.executemany("INSERT OR REPLACE INTO photos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        db.execute("INSERT INTO albums VALUES (?,?,?,?,?)", (name, a.get("title"), a["output_file"], a["folder"], len(photos)))
        for p in glob.glob(os.path.join(d, "jpg", "*.jpg")):
            snapshot_album[os.path.splitext(os.path.basename(p))[0]] = name
    # every original: registered snapshots (id → file) first, then unregistered files
    registered = common.load_snapshots()
    files_seen = set()
    for sid, entry in registered.items():
        p = common.find_original(sid)
        files_seen.add(p)
        t = common.capture_time(sid)
        db.execute("INSERT OR REPLACE INTO snapshots VALUES (?,?,?,?)",
                   (sid, os.path.relpath(p, common.ROOT) if p else None, t.isoformat() if t else None,
                    snapshot_album.get(sid, entry.get("album"))))
    for folder in (common.NEW, common.USED):
        for p in sorted(glob.glob(os.path.join(folder, "*"))):
            if not p.lower().endswith(common.IMAGE_EXT) or p in files_seen:
                continue
            s = os.path.splitext(os.path.basename(p))[0]
            db.execute("INSERT OR IGNORE INTO snapshots VALUES (?,?,?,?)",
                       (s, os.path.relpath(p, common.ROOT), None, None))
    db.commit()
    db.close()
    os.replace(tmp, DB)


def update_caption(name, j, text):
    """Quick update of one caption (from the captioning window) without a full rebuild."""
    if not os.path.exists(DB):
        return
    a, d = common.load_album(name), common.album_dir(name)
    chapters = {f: a["chapters"][c - 1] for f, c, _ in common.album_photos(a, d)[0]}
    year, ysrc = common.year(text, chapters.get(j), a)
    db = sqlite3.connect(DB)
    db.execute("UPDATE photos SET caption=?, caption_source=?, year=?, year_source=? WHERE id=? AND album=?",
               (text, "captioning", year, ysrc, j, name))
    db.commit()
    db.close()


if __name__ == "__main__":
    build()
    db = sqlite3.connect(DB)
    print(f"Inventory: {os.path.relpath(DB, common.ROOT)}")
    for name, title, n in db.execute("SELECT name, title, photo_count FROM albums"):
        def q(sql):
            return db.execute(sql, (name,)).fetchone()[0]
        empty = q("SELECT count(*) FROM uncaptioned WHERE album=?")
        no_year = q("SELECT count(*) FROM photos WHERE album=? AND kind != 'back' AND year IS NULL")
        backs = q("SELECT count(*) FROM photos WHERE album=? AND kind = 'back'")
        print(f"  {title}: {n} photos, uncaptioned {empty}, without year {no_year}, back sides {backs}")
    s, free = db.execute("SELECT count(*), sum(album IS NULL) FROM snapshots").fetchone()
    print(f"  Original snapshots: {s}, not in any album yet: {free or 0}")
