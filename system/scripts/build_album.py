"""Builds the album from system/work/<album>/album.json and the processed photos.

  system/.venv/bin/python system/scripts/build_album.py <album>            finished album file (+ folder version)
  system/.venv/bin/python system/scripts/build_album.py <album> --html-only   only regenerate the HTML

Output:
  Albums/<output_file>              finished album — ONE self-contained offline HTML file (photos
                                      inside), opens in any browser without internet; for your family
  system/folder_version/<folder>/  the same album as a folder (index.html + WebP files); used by the
                                      captioning window. Nothing is uploaded or published.
  Albums/Photos with captions/<folder>/   full-size JPGs with captions in their metadata
  system/work/inventory.db                 the inventory is refreshed
"""
import base64
import html
import json
import os
import re
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def css_string(text):
    """Text for a CSS content:"…" string: quotes and backslashes escaped, no line breaks,
    and no '<' (so it can never close the <style> element)."""
    return (str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
            .replace("<", "\\3C "))


def esc(value):
    """HTML-escapes any value from album.json — numbers too ("date": 1975)."""
    return html.escape("" if value is None else str(value))


def fit(img, max_side):
    """Shrinks an image so its longer side is at most max_side (never enlarges)."""
    h, w = img.shape[:2]
    k = min(1.0, max_side / max(h, w))
    return cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else img


def data_uri(img, max_side, quality):
    ok, buf = cv2.imencode(".webp", fit(img, max_side), [cv2.IMWRITE_WEBP_QUALITY, quality])
    return "data:image/webp;base64," + base64.b64encode(buf).decode()


class Album:
    def __init__(self, name):
        self.name = name
        self.d = common.album_dir(name)
        self.a = common.load_album(name)
        self.files = os.path.join(common.FOLDERS, self.a["folder"])
        self.backs = common.backs(self.d)
        self.back_of = common.back_of(self.a, self.d)   # displayed front (after close-ups) → back
        self.sub = self.a["use_closeup"]
        self.uris = {}                                    # embedded images, encoded once per build

    # ---------- images ----------

    @staticmethod
    def save_webp(img, path, max_side, quality=82):
        img = fit(img, max_side)
        cv2.imwrite(path, img, [cv2.IMWRITE_WEBP_QUALITY, quality])
        return img.shape[1], img.shape[0]

    def check_sources(self, ids, pages):
        """Clear message instead of a crash when album.json names a photo that does not exist."""
        missing = [j for j in list(ids) + list(self.backs) if not common.crop_source(self.d, j)]
        missing += [p for p in pages if not common.snapshot_dir(self.d, p)]
        if missing:
            sys.exit(f"album.json names photos that do not exist in any album: {', '.join(missing)}")

    def ensure_enhanced(self, ids):
        """Every photo in the album gets an up-to-date processed version before building:
        - clippings and back sides: always the gentle version (cheap; correct even if they were
          marked after enhance.py ran)
        - other photos: processed again when the processed file is missing or older than the crop
          (e.g. after a corrected crop) — with the look chosen in the settings."""
        import enhance
        gentle = enhance.gentle_ids(self.a, self.d)
        pipe = enhance.Pipeline(common.load_config())
        for j in list(ids) + list(self.backs):
            x = common.photo_dir(self.d, j)
            crop_p = os.path.join(x, "crops", f"{j}.jpg")
            fin_p, enh_p = os.path.join(x, "final", f"{j}.jpg"), os.path.join(x, "enhanced", f"{j}.jpg")
            done = fin_p if os.path.exists(fin_p) else enh_p
            stale = not os.path.exists(done) or os.path.getmtime(done) < os.path.getmtime(crop_p)
            if j in gentle or stale:
                note = enhance.process_photo(self.d, j, pipe, j in gentle)
                if stale:
                    print(f"{j}: processed ({note})")

    def page_path(self, p):
        return os.path.join(common.snapshot_dir(self.d, p), "jpg", f"{p}.jpg")

    def prepare_images(self, ids, pages):
        for sub in ("photo", "thumb", "original", "pages"):
            os.makedirs(os.path.join(self.files, sub), exist_ok=True)
        sizes = {}
        for j in ids:
            img = cv2.imread(common.best_source(self.d, j))
            sizes[j] = self.save_webp(img, os.path.join(self.files, "photo", f"{j}.webp"), 1600)
            self.save_webp(img, os.path.join(self.files, "thumb", f"{j}.webp"), 640, 78)
            self.uris[("photo", j)] = data_uri(img, 1400, 80)
            self.save_webp(cv2.imread(common.crop_source(self.d, j)), os.path.join(self.files, "original", f"{j}.webp"), 1600)
        for b in self.backs:
            img = cv2.imread(common.best_source(self.d, b))
            self.save_webp(img, os.path.join(self.files, "photo", f"{b}.webp"), 1600)
            self.uris[("photo", b)] = data_uri(img, 1400, 80)
        for p in pages:
            img = cv2.imread(self.page_path(p))
            self.save_webp(img, os.path.join(self.files, "pages", f"{p}.webp"), 1800, 80)
            self.uris[("page", p)] = data_uri(img, 1600, 78)
        json.dump(sizes, open(os.path.join(self.d, "sizes.json"), "w"))
        return sizes

    def uri(self, kind, j):
        if (kind, j) not in self.uris:   # --html-only: not prepared in this run
            src = self.page_path(j) if kind == "page" else common.best_source(self.d, j)
            self.uris[(kind, j)] = data_uri(cv2.imread(src), 1600 if kind == "page" else 1400, 78 if kind == "page" else 80)
        return self.uris[(kind, j)]

    def needs_images(self, sizes):
        """True when the folder version lacks images the album now needs (new photos, pages or
        back sides since the last full build)."""
        photos, pages = common.album_photos(self.a, self.d)
        need = [os.path.join(self.files, "photo", f"{j}.webp") for j, _, _ in photos]
        need += [os.path.join(self.files, "photo", f"{b}.webp") for b in self.backs]
        need += [os.path.join(self.files, "pages", f"{p}.webp") for p in pages]
        return any(j not in sizes for j, _, _ in photos) or not all(os.path.exists(p) for p in need)

    # ---------- HTML ----------

    def figure(self, j, sizes, featured=False):
        w, h = sizes[j]
        cls = "photo" + (" clipping" if j in self.clips else "")
        cap = common.caption(self.a, j, self.caps)
        back = f' data-back="photo/{self.back_of[j]}.webp"' if j in self.back_of else ""
        e = esc
        return (f'<figure class="{cls}" data-id="{j}"{back} style="--r:{w / h:.3f}">'
                f'<img src="thumb/{j}.webp" data-full="photo/{j}.webp" width="{w}" height="{h}" '
                f'loading="lazy" decoding="async" alt="{e(cap or j)}">'
                f'<figcaption>{e(cap)}<span class="label">{j}</span></figcaption></figure>')

    def html(self, sizes, captioning=False):
        self.caps = common.load_captions()
        self.clips = common.clippings(self.a, self.d)
        e = esc
        a, groups, sections = self.a, {}, []
        skip = set(self.backs)
        for i, ch in enumerate(a["chapters"], 1):
            cid = f"c{i}"
            group = ch.get("group", "")
            groups.setdefault(group, []).append((cid, ch["title"]))
            parts = [f'<section class="chapter" id="{cid}">',
                     f'<header><p class="group">{e(str(group))}</p><h2>{e(ch["title"])}</h2>']
            if ch.get("date"):
                parts.append(f'<p class="date">{e(ch["date"])}</p>')
            parts.append("</header>")
            if ch.get("album_caption"):
                parts.append(f'<blockquote class="album-caption">{e(ch["album_caption"])}</blockquote>')
            featured = [self.sub.get(j, j) for j in ch.get("featured", []) if j not in skip]
            parts.append('<div class="featured">' + "".join(self.figure(j, sizes, True) for j in featured) + "</div>")
            for p in ch.get("pages", []):
                rest = [self.sub.get(j, j) for j in common.page_photos(self.d, p)]
                rest = [j for j in rest if j not in featured and j not in skip]
                parts.append(f'<div class="page"><div class="page-head"><span>Album page {p}</span>'
                             f'<button class="whole" data-src="pages/{p}.webp">whole page</button></div>')
                if rest:
                    parts.append('<div class="grid">' + "".join(self.figure(j, sizes) for j in rest) + "</div>")
                parts.append("</div>")
            grid = [self.sub.get(j, j) for j in ch.get("grid", []) if j not in skip]
            if grid:
                parts.append('<div class="grid">' + "".join(self.figure(j, sizes) for j in grid) + "</div>")
            parts.append("</section>")
            sections.append("\n".join(parts))
        menu = [f'<li><span class="menu-group">{e(str(g))}</span><ul>'
                + "".join(f'<li><a href="#{cid}">{e(t)}</a></li>' for cid, t in chs) + "</ul></li>"
                for g, chs in groups.items()]
        t = open(os.path.join(common.TEMPLATES, "album.html"), encoding="utf-8").read()
        if captioning:
            t = t.replace("</body>", open(os.path.join(common.TEMPLATES, "captioning.html"), encoding="utf-8").read() + "</body>")
        tip = a.get("tip", "Click a photo to enlarge it. Use the arrow keys to browse; "
                           "the “original” button shows the photo before enhancement.")
        return (t.replace("{{LANG}}", e(a.get("lang", "en")))
                .replace("{{PAGE_TITLE}}", e(a.get("page_title", a.get("title", ""))))
                .replace("{{TITLE}}", e(a.get("title", "")))
                .replace("{{SUBTITLE}}", e(a.get("subtitle", "")))
                .replace("{{INTRO}}", e(a.get("intro", "")))
                .replace("{{TIP}}", e(tip))
                .replace("{{CAPTION_LABEL}}", css_string(a.get("caption_label", "Written in the album")))
                .replace("{{MENU}}", "\n".join(menu))
                .replace("{{CHAPTERS}}", "\n".join(sections)))

    # ---------- single file ----------

    def single_file(self, sizes):
        page = self.html(sizes)
        # encoded once, straight from the processed JPGs (not from the already compressed WebPs);
        # thumbnail and full size share one embedded image so the data is not doubled
        page = re.sub(r'src="thumb/([^"]+)\.webp" data-full="photo/[^"]+"',
                      lambda m: f'src="{self.uri("photo", m.group(1))}" data-full=""', page)
        page = re.sub(r'data-back="photo/([^"]+)\.webp"', lambda m: f'data-back="{self.uri("photo", m.group(1))}"', page)
        page = re.sub(r'data-src="pages/([^"]+)\.webp"', lambda m: f'data-src="{self.uri("page", m.group(1))}"', page)
        page = page.replace("</style>", '#lb [data-act="original"]{display:none!important}</style>')
        page = page.replace("; the “original” button shows the photo before enhancement.", ".")
        path = os.path.join(common.ALBUMS, self.a["output_file"])
        with open(path, "w", encoding="utf-8") as f:
            f.write(page)
        print(f"{os.path.relpath(path, common.ROOT)}: {os.path.getsize(path) / 1e6:.0f} MB")


def build(name, html_only=False):
    """Builds the whole album (also called by the captioning window when the album changed)."""
    common.require_config()
    alb = Album(name)
    photos, pages = common.album_photos(alb.a, alb.d)
    ids = [j for j, _, _ in photos]
    alb.check_sources(ids, pages)
    sizes_file = os.path.join(alb.d, "sizes.json")
    sizes = json.load(open(sizes_file)) if html_only and os.path.exists(sizes_file) else {}
    if not html_only or alb.needs_images(sizes):
        alb.ensure_enhanced(ids)
        sizes = alb.prepare_images(ids, pages)
    with open(os.path.join(alb.files, "index.html"), "w", encoding="utf-8") as f:
        f.write(alb.html(sizes))
    print(f"{len(ids)} photos, {len(pages)} pages, {len(alb.a['chapters'])} chapters")
    alb.single_file(sizes)
    import inventory
    import metadata
    metadata.export_album(name)
    inventory.build()
    return alb


if __name__ == "__main__":
    build(sys.argv[1], "--html-only" in sys.argv)
