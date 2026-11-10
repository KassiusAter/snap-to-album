"""EXPERIMENTAL — albums from your Apple Photos library (macOS Photos app).

Finds trips in the Photos library by time and place, shows which ones are not in any album yet,
and creates an album in the Photos app with all photos of a chosen trip.

  system/.venv/bin/python system/scripts/photos_trips.py list [--min 60] [--top 20]
  system/.venv/bin/python system/scripts/photos_trips.py create <trip number> "<album name>" [--dry-run]

How trips are found (read-only, nothing in the library is changed):
  - a read-only snapshot of the Photos database is used (cloned instantly; the live library is
    never locked or changed, recent changes are included)
  - photos are split into events at gaps of more than 6 hours
  - "home" is the place with photos on the most different days
  - consecutive events more than 50 km from home (less than 48 h apart, less than 400 km from
    each other) are joined into one trip
  - each trip is scored: number of photos, days, distance from home, Apple's own aesthetic
    score and favorites — minus how much of it is already in one of your albums
  - photos taken at airports up to 30 h before or after a trip (departure, arrival) belong to it

Creating an album uses AppleScript (the official way to automate Photos). The album only refers
to photos already in your library — nothing is copied, moved or deleted. Skipped automatically:
  - photos from shared albums of other people (Photos does not allow adding them to your own
    albums; save them to your library first if you want them)
  - hidden frames of burst series (the burst's key photo is included)

Privacy: everything runs on this Mac. Only the summary (dates, Apple's place names, counts) is
shown — and, when Claude runs this, sent to Anthropic as part of the conversation. No photos.
macOS may ask once for permission to control Photos (and, depending on your settings, for Full
Disk Access for the Terminal / Claude to read the library).
"""
import collections
import datetime as dt
import glob
import json
import math
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

EPOCH = dt.datetime(2001, 1, 1)                 # Photos stores times as seconds since 2001 (UTC)
EVENT_GAP, TRIP_GAP = 6 * 3600, 48 * 3600
AWAY_KM, TRIP_SPREAD_KM = 50, 400
AIRPORT_WINDOW = 30 * 3600
AIRPORT_WORDS = ("Letiš", "Airport", "Flughafen", "Luchthaven", "Aeropuert", "Aéroport", "Aeroporto",
                 "Lotnisko", "Letisko", "Lufthavn", "Flygplats")
CACHE = os.path.join(common.WORK, "photos_trips.json")
PERMISSION_HINT = ("Allow Full Disk Access for the Terminal (or the Claude app) in System Settings → "
                   "Privacy & Security → Full Disk Access, then try again.")


def library_path():
    """The System Photo Library: the one the Photos app uses (its bookmark in the Photos
    preferences holds the library name), else 'Photos Library', else the only one."""
    import plistlib
    bookmark = b""
    for pref in ("~/Library/Containers/com.apple.Photos/Data/Library/Preferences/com.apple.Photos.plist",
                 "~/Library/Preferences/com.apple.Photos.plist"):
        try:
            with open(os.path.expanduser(pref), "rb") as f:
                bookmark = plistlib.load(f).get("IPXDefaultLibraryURLBookmark") or b""
            if bookmark:
                break
        except (OSError, ValueError):
            continue
    libs = sorted(glob.glob(os.path.expanduser("~/Pictures/*.photoslibrary")))
    for lib in libs:
        if os.path.basename(lib).encode("utf-8") in bookmark:
            return lib
    default = os.path.expanduser("~/Pictures/Photos Library.photoslibrary")
    if os.path.isdir(default):
        return default
    if len(libs) == 1:
        return libs[0]
    sys.exit("No Photos library found in ~/Pictures (or several — open the one you use in Photos). "
             "If you do have one: " + PERMISSION_HINT)


def library_db():
    """A consistent, read-only snapshot of the Photos database. The database and its write-ahead
    log are cloned (APFS clone: instant, no extra space) into a temporary folder, so recent changes
    are included and the live library is never locked or touched."""
    src = os.path.join(library_path(), "database")
    tmp = tempfile.mkdtemp(prefix="snap-photos-")
    try:
        for f in ("Photos.sqlite", "Photos.sqlite-wal", "Photos.sqlite-shm"):
            if os.path.exists(os.path.join(src, f)):
                if subprocess.run(["cp", "-c", os.path.join(src, f), tmp], capture_output=True).returncode:
                    shutil.copy2(os.path.join(src, f), tmp)
        db = sqlite3.connect(os.path.join(tmp, "Photos.sqlite"))
        db.execute("SELECT count(*) FROM ZASSET").fetchone()
    except (OSError, sqlite3.Error) as e:
        shutil.rmtree(tmp, ignore_errors=True)
        sys.exit(f"Cannot read the Photos library ({e}). " + PERMISSION_HINT)
    import atexit
    atexit.register(shutil.rmtree, tmp, True)
    return db


def when(seconds, offset=0):
    """Local time where the photo was taken (Photos stores UTC plus the time-zone offset)."""
    return EPOCH + dt.timedelta(seconds=seconds + (offset or 0))


def has_gps(la, lo):
    return (la is not None and lo is not None and -90 <= la <= 90 and -180 < lo <= 180
            and not (la == 0 and lo == 0) and la != -180)


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    return 12742 * math.asin(math.sqrt(math.sin((la2 - la1) / 2) ** 2
                                       + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2))


def load(db):
    """All visible photos and videos of the library, oldest first:
    (uuid, utc seconds, lat, lon, aesthetic, favorite, place, pk, shared, burst_hidden, tz offset, kind)"""
    return db.execute("""
        SELECT a.ZUUID, a.ZDATECREATED, a.ZLATITUDE, a.ZLONGITUDE, coalesce(a.ZOVERALLAESTHETICSCORE, 0),
               coalesce(a.ZFAVORITE, 0), coalesce(m.ZTITLE, ''), a.Z_PK,
               coalesce(a.ZSAVEDASSETTYPE, 0) = 4 AS shared,
               coalesce(a.ZAVALANCHEKIND, 0) = 1 AND coalesce(a.ZVISIBILITYSTATE, 0) = 2 AS burst_hidden,
               coalesce(aa.ZTIMEZONEOFFSET, 0), a.ZKIND
        FROM ZASSET a
        LEFT JOIN ZMOMENT m ON a.ZMOMENT = m.Z_PK
        LEFT JOIN ZADDITIONALASSETATTRIBUTES aa ON aa.ZASSET = a.Z_PK
        WHERE a.ZTRASHEDSTATE = 0 AND a.ZHIDDEN = 0 AND a.ZDATECREATED > 0
        ORDER BY a.ZDATECREATED""").fetchall()


def album_link_table(db):
    """The table linking photos to albums. Its name carries entity numbers that differ between
    macOS versions (Z_33ASSETS, Z_30ASSETS …), so it is found by its columns."""
    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'Z%ASSETS'"):
        cols = [c[1] for c in db.execute(f'PRAGMA table_info("{name}")')]
        albums = [c for c in cols if c.endswith("ALBUMS")]
        assets = [c for c in cols if c.endswith("ASSETS") and "FOK" not in c]
        if albums and assets:
            return name, albums[0], assets[0]
    return None


def albums_of(db):
    """{photo pk: [album titles]} for your own albums (empty if the layout is unknown)."""
    link = album_link_table(db)
    out = collections.defaultdict(list)
    if not link:
        print("Note: could not read album membership on this macOS version — all trips shown as new.")
        return out
    table, album_col, asset_col = link
    for pk, title in db.execute(f"""SELECT j."{asset_col}", g.ZTITLE FROM "{table}" j
                                    JOIN ZGENERICALBUM g ON g.Z_PK = j."{album_col}"
                                    WHERE g.ZKIND = 2 AND g.ZTRASHEDSTATE = 0"""):
        out[pk].append(title)
    return out


def album_exists(db, name):
    """Any of your albums with this name — also inside folders."""
    return db.execute("SELECT count(*) FROM ZGENERICALBUM WHERE ZKIND = 2 AND ZTRASHEDSTATE = 0 AND ZTITLE = ?",
                      (name,)).fetchone()[0] > 0


def find_trips(rows):
    days = collections.defaultdict(set)
    for r in rows:
        if has_gps(r[2], r[3]):
            days[(round(r[2] / 0.02), round(r[3] / 0.02))].add(int(r[1] // 86400))
    if not days:
        sys.exit("None of your photos has a location, so trips cannot be found. "
                 "(Location for the Camera is set in Settings → Privacy → Location Services on the phone.)")
    cell = max(days, key=lambda c: len(days[c]))
    home = (cell[0] * 0.02, cell[1] * 0.02)
    events, cur, last = [], [], None
    for r in rows:
        if last is not None and r[1] - last > EVENT_GAP:
            events.append(cur)
            cur = []
        cur.append(r)
        last = r[1]
    if cur:
        events.append(cur)

    def center(ev):
        g = sorted((r[2], r[3]) for r in ev if has_gps(r[2], r[3]))
        return g[len(g) // 2] if g else None

    trips = []
    for ev in events:
        c = center(ev)
        near_last = trips and trips[-1]["away"] and ev[0][1] - trips[-1]["end"] < TRIP_GAP
        if c is None and near_last:
            # photos without a location (indoors, screenshots) in the middle of a trip belong to it
            trips[-1]["rows"] += ev
            trips[-1]["end"] = ev[-1][1]
            continue
        away = c is not None and km(c, home) > AWAY_KM
        if away and near_last and km(c, trips[-1]["c"]) < TRIP_SPREAD_KM:
            trips[-1]["rows"] += ev
            trips[-1]["end"] = ev[-1][1]
            trips[-1]["c"] = c
        else:
            trips.append({"rows": list(ev), "end": ev[-1][1], "c": c, "away": away})
    return [t for t in trips if t["away"]], home


def airport_photos(rows, t0, t1, inside):
    return [r for r in rows if r[0] not in inside
            and (t0 - AIRPORT_WINDOW <= r[1] < t0 or t1 < r[1] <= t1 + AIRPORT_WINDOW)
            and any(w in r[6] for w in AIRPORT_WORDS)]


def cmd_list(min_items=60, top=20):
    db = library_db()
    rows, in_albums = load(db), albums_of(db)
    trips, home = find_trips(rows)
    result = []
    for t in trips:
        R = t["rows"]
        if len(R) < min_items:
            continue
        t0, t1 = when(R[0][1], R[0][10]), when(R[-1][1], R[-1][10])
        n_days = (t1.date() - t0.date()).days + 1
        dist = km(t["c"], home)
        own = [r for r in R if not r[8] and not r[9]]   # photos that can be in your albums at all
        covered = sum(1 for r in own if r[7] in in_albums) / max(len(own), 1)
        existing = collections.Counter(a for r in R for a in in_albums.get(r[7], [])).most_common(2)
        places = [p for p, _ in collections.Counter(r[6] for r in R if r[6]).most_common(3)]
        good = sum(1 for r in R if r[4] > 0.5) + sum(r[5] for r in R)
        score = math.log(len(R)) * 2 + min(n_days, 14) * 0.8 + math.log1p(dist) / 1.5 + math.log1p(good) - 6 * covered
        result.append({"from": t0.strftime("%Y-%m-%d %H:%M"), "to": t1.strftime("%Y-%m-%d %H:%M"), "days": n_days,
                       "photos": len(R), "km": round(dist), "in_albums": round(covered, 2),
                       "existing_albums": [a for a, _ in existing], "places": places, "score": round(score, 1),
                       "t0": R[0][1], "t1": R[-1][1]})
    result.sort(key=lambda x: x["score"], reverse=True)
    for i, r in enumerate(result, 1):
        r["number"] = i
    os.makedirs(common.WORK, exist_ok=True)
    json.dump({"home": home, "trips": result}, open(CACHE, "w"), ensure_ascii=False, indent=1)
    print(f"{len(rows)} photos/videos, home ≈ {home[0]:.2f}, {home[1]:.2f}; {len(result)} trips with ≥ {min_items} photos")
    print(f"{sum(1 for r in result if r['in_albums'] >= 0.5)} of them are already mostly in an album.\n")
    print("Best trips not yet in an album:")
    for r in [r for r in result if r["in_albums"] < 0.2][:top]:
        print(f"  #{r['number']:<3} {r['from'][:10]} – {r['to'][:10]} ({r['days']:2} d) | {r['photos']:5} photos | "
              f"{r['km']:5} km | {' / '.join(r['places'])[:60]}")
    partly = [r for r in result if 0.2 <= r["in_albums"] < 0.5]
    if partly:
        print("\nPartly in an album:")
        for r in partly[:top]:
            print(f"  #{r['number']:<3} {r['from'][:10]} ({r['photos']} photos, {r['in_albums']:.0%} in “{r['existing_albums'][0]}”)")


def applescript_add(name, uuids, dry_run):
    lst = ", ".join(f'"{u}/L0/001"' for u in uuids)
    safe = name.replace("\\", "\\\\").replace('"', '\\"')
    finish = ("return (count of found) as text" if dry_run else f'''if (count of found) = 0 then error "None of the photos could be found in Photos."
	set alb to make new album named "{safe}"
	try
		add found to alb
	on error msg
		delete alb
		error msg
	end try
	return (count of media items of alb) as text''')
    script = f'''tell application "Photos"
	set found to {{}}
	repeat with i in {{{lst}}}
		try
			set end of found to media item id (contents of i)
		end try
	end repeat
	{finish}
end tell'''
    try:
        out = subprocess.run(["osascript", "-"], input=script, capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired:
        sys.exit("Photos took too long. Please try again (Photos may still be downloading from iCloud).")
    if out.returncode:
        sys.exit(f"Photos refused: {out.stderr.strip()}")
    return int(out.stdout.strip() or 0)


def cmd_create(number, name, dry_run=False):
    if not os.path.exists(CACHE):
        sys.exit("Run 'photos_trips.py list' first.")
    trip = next((t for t in json.load(open(CACHE))["trips"] if t["number"] == number), None)
    if not trip:
        sys.exit(f"No trip #{number} in the last list.")
    db = library_db()
    if album_exists(db, name):
        sys.exit(f"An album named “{name}” already exists in Photos. Choose another name.")
    rows = load(db)
    inside = {r[0] for r in rows if trip["t0"] <= r[1] <= trip["t1"]}
    trip_rows = [r for r in rows if r[0] in inside]
    airport = airport_photos(rows, trip["t0"], trip["t1"], inside)
    chosen = trip_rows + airport
    shared = sum(1 for r in chosen if r[8])
    bursts = sum(1 for r in chosen if r[9] and not r[8])
    uuids = [r[0] for r in chosen if not r[8] and not r[9]]
    n = applescript_add(name, uuids, dry_run)
    print(f"{'Would create' if dry_run else 'Created'} “{name}”: {n} photos "
          f"(trip {len(trip_rows)}, airports {len(airport)}; skipped {shared} from other people's shared albums, "
          f"{bursts} hidden burst frames)")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["list"]:
        opt = dict(zip(args[1::2], args[2::2]))
        cmd_list(int(opt.get("--min", 60)), int(opt.get("--top", 20)))
    elif args[:1] == ["create"] and len(args) >= 3:
        cmd_create(int(args[1].lstrip("#")), args[2], "--dry-run" in args)
    else:
        sys.exit(__doc__)
