"""Captioning window: add captions right inside the album, in the browser.

Starts a small web server on THIS computer only (127.0.0.1 — not reachable from the network)
and opens the album with a text field under every photo. Enter saves the caption and jumps
to the next photo. Each caption is saved:
  - immediately to system/work/captions.json (one file for all albums, keyed by photo id, so a
    caption stays with its photo even when the photo moves to another chapter or album) and to
    the album's folder version
  - a moment later (after 2 s without typing, and always when the window is closed) to the
    finished album file in Albums/, the photo's metadata and the inventory — so typing stays
    fast even when the album file is large

  system/.venv/bin/python system/scripts/caption_server.py <album>
Easier: double-click "Albums/<album> – add captions.command" (made by make_launcher.py).
Stop: close the Terminal window (or Ctrl+C). Nothing is lost — every Enter is saved.
"""
import fcntl
import html
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import zlib
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import inventory  # noqa: E402
import metadata  # noqa: E402
from build_album import Album  # noqa: E402

ALB = Album(sys.argv[1])
# preferred port per album; if another program (or another album's window) uses it,
# the next free port is taken — two captioning windows never mix
PORT = 8765 + zlib.crc32(ALB.name.encode()) % 1000
PHOTO_IDS = {j for j, _, _ in common.album_photos(ALB.a, ALB.d)[0]}
FIGURE = re.compile(r'(<figure class="[^"]*" data-id="([^"]+)"[^>]*><img [^>]*? alt=")[^"]*'
                    r'("><figcaption>)[^<]*(<span class="label">)')


def atomic_write(path, text):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=os.path.splitext(path)[1])
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


@contextmanager
def saving_lock():
    """One save at a time — across threads and across captioning windows of other albums,
    which share captions.json. Prevents two quick Enters from overwriting each other."""
    os.makedirs(common.WORK, exist_ok=True)
    with open(os.path.join(common.WORK, ".captions.lock"), "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def save_caption(j, text):
    # an empty caption is stored too: it means "deleted on purpose" and overrides any
    # caption Claude wrote into album.json
    data = common.load_captions()
    data[j] = text
    atomic_write(common.CAPTIONS, json.dumps(dict(sorted(data.items())), ensure_ascii=False, indent=1))


def albums_with(j):
    """Every album that shows photo j (a photo can be listed in more than one album)."""
    found = []
    for name in common.album_names():
        a = common.load_album(name)
        if j in {p for p, _, _ in common.album_photos(a, common.album_dir(name))[0]}:
            found.append((name, a))
    return found or [(ALB.name, ALB.a)]


def write_into_albums(captions, albums=None, kinds=("album", "folder")):
    """Puts captions {id: text} straight into the album files (no rebuild) — of this album or of
    the given albums; "album" = the finished single file, "folder" = the folder version."""
    def repl(m):
        j = html.unescape(m.group(2))
        if j not in captions:
            return m.group(0)
        t = captions[j]
        return m.group(1) + html.escape(t or j) + m.group(3) + html.escape(t) + m.group(4)
    changed = 0
    paths = []
    for _, a in (albums or [(ALB.name, ALB.a)]):
        if "album" in kinds:
            paths.append(os.path.join(common.ALBUMS, a["output_file"]))
        if "folder" in kinds:
            paths.append(os.path.join(common.FOLDERS, a["folder"], "index.html"))
    for path in paths:
        if os.path.exists(path):
            old = open(path, encoding="utf-8").read()
            new = FIGURE.sub(repl, old)
            if new != old:
                atomic_write(path, new)
                changed += 1
    return changed


MAX_CAPTION = 2000  # characters
PENDING = {}         # id → caption, still to be written into the big album files
PENDING_LOCK = threading.Lock()
TIMER = None


def flush():
    """Writes waiting captions into the finished album files, metadata and inventory."""
    with PENDING_LOCK:
        items = dict(PENDING)
        PENDING.clear()
    if not items:
        return
    with saving_lock():
        by_album = {}
        for j, text in items.items():
            for name, a in albums_with(j):
                by_album.setdefault(name, (a, {}))[1][j] = text
        for name, (a, caps) in by_album.items():
            write_into_albums(caps, [(name, a)], kinds=("album",))
            if a.get("source") == "photos":
                # albums made from the Photos app: the caption also goes onto the original photo there
                import photos_captions
                sent = photos_captions.write(photos_captions.for_album(name, caps))
                print(f"  {sent} caption(s) written into the Photos app")
            for j, text in caps.items():
                try:
                    metadata.update(name, j)
                    inventory.update_caption(name, j, text)
                except Exception as e:  # noqa: BLE001 — caption is saved; catches up on the next build
                    print(f"  metadata/inventory not updated for {j}: {e}")


def schedule_flush(delay=2.0):
    global TIMER
    with PENDING_LOCK:
        if TIMER:
            TIMER.cancel()
        TIMER = threading.Timer(delay, flush)
        TIMER.daemon = True
        TIMER.start()


def flush_and_exit(*_):
    """Closing the Terminal window (or Ctrl+C) still writes every waiting caption first."""
    flush()
    print("\nStopped. All captions are saved.")
    os._exit(0)


class Handler(SimpleHTTPRequestHandler):
    def own_host(self):
        """Only requests addressed to this server itself (blocks DNS-rebinding tricks)."""
        return self.headers.get("Host", "") in (f"127.0.0.1:{PORT}", f"localhost:{PORT}")

    def own_page(self):
        """Saving is allowed only from the captioning page: JSON body (browsers cannot send that
        cross-site without permission, which this server never grants) and, if the browser says
        where the request comes from, it must be this server."""
        origin = self.headers.get("Origin")
        return (self.own_host() and self.headers.get("Content-Type", "").startswith("application/json")
                and (origin is None or origin in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}")))

    def do_GET(self):
        if not self.own_host():
            self.send_error(403)
            return
        if self.path in ("/", "/index.html"):
            sizes = json.load(open(os.path.join(ALB.d, "sizes.json")))
            body = ALB.html(sizes, captioning=True).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

    def do_POST(self):
        if self.path != "/caption":
            self.send_error(404)
            return
        if not self.own_page():
            self.send_error(403)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 4 * MAX_CAPTION + 200:
                raise ValueError("request too large")
            d = json.loads(self.rfile.read(length))
            j, text = str(d["id"]), str(d.get("text", "")).strip()[:MAX_CAPTION]
            if j not in PHOTO_IDS:
                raise ValueError(f"unknown photo {j}")
            with saving_lock():
                save_caption(j, text)                                  # the record — immediately
                write_into_albums({j: text}, albums_with(j), kinds=("folder",))
            with PENDING_LOCK:
                PENDING[j] = text
            schedule_flush()
        except Exception as e:  # noqa: BLE001
            # the HTTP status line only allows plain ASCII
            self.send_error(400, str(e).encode("ascii", "replace").decode())
            return
        print(f"  saved {j}: {text}")
        body = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    sizes_file = os.path.join(ALB.d, "sizes.json")
    sizes = json.load(open(sizes_file)) if os.path.exists(sizes_file) else {}
    if ALB.needs_images(sizes):
        # the album changed since its last build (or was never built) — bring it up to date first
        print("Updating the album first, one moment…")
        import build_album
        ALB = build_album.build(ALB.name)
    # an older captioning window for THIS album may still be running — stop only that one,
    # so the current version of this script serves. Other albums' windows and other programs
    # are never touched.
    out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout
    for line in out.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if "caption_server.py " not in cmd or int(pid) == os.getpid():
            continue
        # everything after the script name is the album name (it may contain spaces)
        if cmd.split("caption_server.py ", 1)[1].strip() == ALB.name:
            subprocess.run(["kill", pid])   # SIGTERM: the old window writes its waiting captions first
    server = None
    for attempt in range(40):
        port = PORT + attempt // 2           # each port is tried twice (an old window may be closing)
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=ALB.files))
            PORT = port
            break
        except OSError:
            time.sleep(0.25)
    if server is None:
        sys.exit("No free port found — please close other captioning windows and try again.")
    url = f"http://127.0.0.1:{PORT}/"
    write_into_albums(common.load_captions())  # catch up captions saved earlier
    for sig in (signal.SIGHUP, signal.SIGTERM):
        signal.signal(sig, flush_and_exit)
    print(f"Captioning “{ALB.a.get('title', ALB.name)}” at {url}")
    print("Close this window when you are done. Every caption is saved on Enter.")
    subprocess.run(["open", url])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        flush_and_exit()
