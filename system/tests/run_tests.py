"""Snap to Album self-test — no personal photos needed.

  system/.venv/bin/python system/tests/run_tests.py

Builds synthetic snapshots (an album page with three prints, a loose print, the back of a print),
copies the scripts into a temporary project and runs the whole paper-album workflow there:
convert → detect → backs → enhance → build → captioning window (HTTP) → move_used → inventory.
Plus unit tests of the pure helpers. The Apple Photos scripts are tested only where they need no
Photos library (photo picking). Nothing outside the temporary folder is touched.
"""
import http.client
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SYSTEM = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SYSTEM, "scripts"))
import common  # noqa: E402
import photos_album  # noqa: E402


# ---------- synthetic images ----------

def print_content(w, h, seed):
    """A 'photo': gradient sky, dark ground, a face-like disc — enough contrast to be a photo."""
    rng = np.random.default_rng(seed)
    img = np.zeros((h, w, 3), np.uint8)
    for y in range(h):
        img[y, :] = (200 - 120 * y // h, 170 - 60 * y // h, 140 + 60 * y // h)
    cv2.rectangle(img, (0, int(h * 0.6)), (w, h), (40, 70, 50), -1)
    cx, cy, r = int(w * rng.uniform(0.3, 0.7)), int(h * 0.45), int(min(w, h) * 0.18)
    cv2.circle(img, (cx, cy), r, (150, 180, 220), -1)
    cv2.circle(img, (cx - r // 3, cy - r // 4), r // 8, (40, 40, 60), -1)
    cv2.circle(img, (cx + r // 3, cy - r // 4), r // 8, (40, 40, 60), -1)
    return img


def framed(content, border=18):
    h, w = content.shape[:2]
    out = np.full((h + 2 * border, w + 2 * border, 3), 245, np.uint8)
    out[border:border + h, border:border + w] = content
    return out


def album_page():
    page = np.full((1800, 2400, 3), (28, 30, 36), np.uint8)
    for i, (x, y, w, h) in enumerate([(120, 120, 900, 650), (1250, 150, 1000, 700), (300, 950, 800, 600)]):
        page[y:y + h, x:x + w] = framed(print_content(w - 36, h - 36, i))
    return page


def loose_print():
    snap = np.full((1500, 2000, 3), (22, 24, 30), np.uint8)
    snap[250:1250, 400:1600] = framed(print_content(1164, 964, 7))
    return snap


def back_side():
    """Plain paper with a few thin handwritten lines."""
    snap = np.full((1500, 2000, 3), (22, 24, 30), np.uint8)
    paper = np.full((1000, 1200, 3), (215, 222, 232), np.uint8)
    for k in range(3):   # thin, pencil-like handwriting (a real back is mostly plain paper)
        cv2.putText(paper, "Aunt Mary, 1962", (120, 300 + 180 * k), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (120, 110, 130), 2)
    snap[250:1250, 400:1600] = paper
    return snap


# ---------- the temporary project ----------

class Project:
    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="snap-test-")
        sysdir = os.path.join(self.root, "system")
        shutil.copytree(os.path.join(SYSTEM, "scripts"), os.path.join(sysdir, "scripts"))
        shutil.copytree(os.path.join(SYSTEM, "templates"), os.path.join(sysdir, "templates"))
        for d in ("New photos", "Albums"):
            os.makedirs(os.path.join(self.root, d))
        fake = os.path.join(self.root, "fakebin")      # a harmless 'open' so no browser pops up
        os.makedirs(fake)
        with open(os.path.join(fake, "open"), "w") as f:
            f.write("#!/bin/sh\n")
        os.chmod(os.path.join(fake, "open"), 0o755)
        self.env = dict(os.environ, PATH=fake + os.pathsep + os.environ["PATH"])
        json.dump({"enhancement": "colors", "view_photos": "no", "time_source": "name", "back_max_gap": 0},
                  open(os.path.join(sysdir, "config.json"), "w"))

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def run(self, script, *args, check=True):
        cmd = [sys.executable, self.path("system", "scripts", script + ".py")] + list(args)
        res = subprocess.run(cmd, cwd=self.root, env=self.env, capture_output=True, text=True, timeout=600)
        if check and res.returncode:
            raise AssertionError(f"{script} {' '.join(args)} failed:\n{res.stdout}\n{res.stderr}")
        return res

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


EXIFTOOL = shutil.which("exiftool")


def exif_description(path):
    if not EXIFTOOL:
        return None
    return subprocess.run([EXIFTOOL, "-s3", "-Description", path], capture_output=True, text=True).stdout.strip()


class PaperAlbumWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = Project()
        for name, img in (("IMG_0001", album_page()), ("IMG_0002", loose_print()), ("IMG_0003", back_side())):
            cv2.imwrite(cls.p.path("New photos", f"{name}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 95])

    @classmethod
    def tearDownClass(cls):
        cls.p.cleanup()

    def test_01_convert(self):
        out = self.p.run("convert", "t").stdout
        self.assertIn("3 snapshots", out)
        self.assertEqual(len(os.listdir(self.p.path("system", "work", "t", "jpg"))), 3)

    def test_02_detect(self):
        out = self.p.run("detect_photos", "t").stdout
        self.assertIn("IMG_0001: 3 photo(s) [page]", out)
        self.assertIn("IMG_0002: 1 photo(s) [single]", out)
        self.assertIn("IMG_0003: 1 photo(s) [single]", out)
        self.assertTrue(os.path.exists(self.p.path("system", "work", "t", "check", "_overview.jpg")))

    def test_03_backs(self):
        self.p.run("backs", "t")
        proposal = json.load(open(self.p.path("system", "work", "t", "backs_proposal.json")))
        self.assertEqual(proposal["backs"], {"IMG_0003_1": "IMG_0002_1"}, proposal)
        json.dump(proposal["backs"], open(self.p.path("system", "work", "t", "backs.json"), "w"))

    def test_04_enhance(self):
        out = self.p.run("enhance", "t").stdout
        self.assertIn("IMG_0003_1: clipping", out)          # the back side gets the gentle treatment
        self.assertIn("IMG_0002_1: color", out)
        sig = open(self.p.path("system", "work", "t", "enhanced", "IMG_0003_1.cfg")).read()
        self.assertTrue(sig.startswith("gentle|"))

    def test_05_build(self):
        album = {"title": "Test", "output_file": "1975 Test.html", "folder": "test",
                 "caption_label": "Grandma's \"notes\" & more",
                 "captions": {"IMG_0001_2": "Written by Claude, 1975"},
                 "chapters": [{"group": 1975, "title": "Page", "date": 1975, "pages": ["IMG_0001"]},
                              {"group": "Loose", "title": "Loose print", "featured": ["IMG_0002_1"]}]}
        json.dump(album, open(self.p.path("system", "work", "t", "album.json"), "w"))
        out = self.p.run("build_album", "t").stdout
        self.assertIn("4 photos, 1 pages, 2 chapters", out)
        page = open(self.p.path("Albums", "1975 Test.html"), encoding="utf-8").read()
        self.assertEqual(page.count("<figure "), 4)
        self.assertIn('data-id="IMG_0002_1" data-back="data:image/webp', page)   # back side embedded
        self.assertIn("Written by Claude, 1975", page)
        self.assertIn('content:"Grandma\'s \\"notes\\" & more"', page)
        self.assertTrue(os.path.exists(self.p.path("system", "folder_version", "test", "index.html")))
        exported = self.p.path("Albums", "Photos with captions", "test")
        self.assertTrue(os.path.exists(os.path.join(exported, "IMG_0002_1_back.jpg")))
        if EXIFTOOL:
            self.assertEqual(exif_description(os.path.join(exported, "IMG_0001_2.jpg")), "Written by Claude, 1975")

    def test_06_settings_change_reprocesses(self):
        cfg_path = self.p.path("system", "config.json")
        cfg = json.load(open(cfg_path))
        cfg["enhancement"] = "none"
        json.dump(cfg, open(cfg_path, "w"))
        out = self.p.run("build_album", "t").stdout
        self.assertIn("settings changed", out)
        self.assertEqual(open(self.p.path("system", "work", "t", "enhanced", "IMG_0002_1.cfg")).read(),
                         "none|colorize=off|upscale=off")
        self.assertNotIn("settings changed", self.p.run("build_album", "t").stdout)   # second build: nothing to do

    def test_07_captioning_window(self):
        self.p.run("make_launcher", "t")
        self.assertTrue(os.path.exists(self.p.path("Albums", "1975 Test – add captions.command")))
        proc = subprocess.Popen([sys.executable, "-u", self.p.path("system", "scripts", "caption_server.py"), "t"],
                                cwd=self.p.root, env=self.p.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        port = None
        for _ in range(100):
            line = proc.stdout.readline()
            if not line:
                break
            if "at http://127.0.0.1:" in line:
                port = int(line.split("127.0.0.1:")[1].split("/")[0])
                break
        self.assertIsNotNone(port, "captioning window did not start")
        try:
            def post(body, origin=f"http://127.0.0.1:{{port}}", ctype="application/json"):
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                headers = {"Content-Type": ctype, "Host": f"127.0.0.1:{port}", "Origin": origin.format(port=port)}
                c.request("POST", "/caption", json.dumps(body), headers)
                return c.getresponse().status

            self.assertEqual(post({"id": "IMG_0001_1", "text": "Grandpa at the lake, summer 1962"}), 200)
            self.assertEqual(post({"id": "IMG_0001_1", "text": "x"}, origin="https://evil.example"), 403)
            self.assertEqual(post({"id": "../x", "text": "x"}), 400)
            self.assertEqual(post({"id": "IMG_0001_2", "text": ""}), 200)   # delete Claude's caption
            folder_index = open(self.p.path("system", "folder_version", "test", "index.html"), encoding="utf-8").read()
            self.assertIn("Grandpa at the lake, summer 1962", folder_index)   # immediately
            time.sleep(3.5)                                                     # debounced writes
            album_file = open(self.p.path("Albums", "1975 Test.html"), encoding="utf-8").read()
            self.assertIn("Grandpa at the lake, summer 1962", album_file)
            self.assertNotIn("Written by Claude, 1975", album_file)
            caps = json.load(open(self.p.path("system", "work", "captions.json")))
            self.assertEqual(caps, {"IMG_0001_1": "Grandpa at the lake, summer 1962", "IMG_0001_2": ""})
            if EXIFTOOL:
                self.assertEqual(exif_description(self.p.path("Albums", "Photos with captions", "test", "IMG_0001_1.jpg")),
                                 "Grandpa at the lake, summer 1962")
        finally:
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=20)

    def test_08_move_used_and_inventory(self):
        out = self.p.run("move_used", "t").stdout
        self.assertIn("Moved 3 originals", out)
        self.assertEqual(os.listdir(self.p.path("New photos")), [])
        out = self.p.run("inventory").stdout
        self.assertIn("Test: 4 photos, uncaptioned 3, without year 1, back sides 1", out)   # the loose print has no year
        self.assertIn("Original snapshots: 3, not in any album yet: 0", out)

    def test_09_same_name_later(self):
        """A different photo with an already used file name gets its own id — nothing is overwritten."""
        cv2.imwrite(self.p.path("New photos", "IMG_0002.jpg"), loose_print(), [cv2.IMWRITE_JPEG_QUALITY, 95])
        out = self.p.run("convert", "t").stdout
        self.assertIn("IMG_0002.jpg → snapshot id IMG_0002-2", out)
        self.p.run("move_used", "t")
        self.assertEqual(sorted(os.listdir(self.p.path("system", "used photos"))),
                         ["IMG_0001.jpg", "IMG_0002 (2).jpg", "IMG_0002.jpg", "IMG_0003.jpg"])


class Helpers(unittest.TestCase):
    def test_year(self):
        self.assertEqual(common.year("Grandma in the 1950s")[0], 1950)
        self.assertEqual(common.year("summer 1962, still there (2026)")[0], 1962)
        self.assertEqual(common.year("", {"group": 1975})[0], 1975)
        self.assertEqual(common.year("", None, {"title": "Lisbon 2019"})[0], 2019)
        self.assertEqual(common.year("room 21950"), (None, None))

    def test_safe_id(self):
        self.assertEqual(common.safe_id("IMG_0012"), "IMG_0012")
        self.assertEqual(common.safe_id("Grand-mère & Père #2"), "Grand-mere-Pere-2")

    def test_register_snapshot(self):
        m = {}
        self.assertEqual(common.register_snapshot("IMG_0012.HEIC", "a", m), "IMG_0012")
        self.assertEqual(common.register_snapshot("IMG_0012.HEIC", "a", m), "IMG_0012")       # same file again
        m["IMG_0012"]["where"] = "used"
        self.assertEqual(common.register_snapshot("IMG_0012.HEIC", "a", m), "IMG_0012-2")     # a new photo, old name

    def test_pick_photos(self):
        import datetime as dt
        rows = []
        for day in range(3):
            for k in range(40):
                t = day * 86400 + k * 30                                  # a photo every 30 s
                rows.append({"uuid": f"u{day}-{k}", "t": t, "time": dt.datetime(2020, 1, 1 + day),
                             "day": dt.date(2020, 1, 1 + day), "place": "", "score": (k % 7) / 10})
        picked = photos_album.pick(rows, 30)
        self.assertEqual(len(picked), 30)
        self.assertEqual(len({r["day"] for r in picked}), 3)                   # every day represented
        # at most one photo per group of near-duplicates (a group = photos within 90 s of its first photo)
        groups = []
        for r in rows:
            if groups and r["t"] - groups[-1][0]["t"] <= photos_album.DUPLICATE_GAP:
                groups[-1].append(r)
            else:
                groups.append([r])
        chosen = {r["uuid"] for r in picked}
        self.assertTrue(all(sum(r["uuid"] in chosen for r in g) <= 1 for g in groups))
        self.assertTrue(all(r["score"] == max(x["score"] for x in g) for g in groups for r in g if r["uuid"] in chosen))


if __name__ == "__main__":
    unittest.main(verbosity=2)
