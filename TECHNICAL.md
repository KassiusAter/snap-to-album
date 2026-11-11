# Snap to Album — technical reference

Everything a curious user or a developer may want to know. Normal use needs none of it: Claude runs
all of this for you.

## Requirements

- macOS (uses the built-in `sips` to read HEIC, JPG, PNG and TIFF); Apple Silicon recommended for GPU speed.
  Windows and Linux versions are in the works: the core (detection, restoration, AI models, album
  building) is plain Python; what still needs porting is HEIC conversion, the double-click launchers,
  the setup script and a few system calls in the captioning window.
- Photos from any phone (iPhone, Android), camera or scanner
- Python 3.10 or newer (tested with 3.14), ~2 GB free disk space
- [Claude Code](https://claude.com/claude-code) (terminal or the Claude desktop app). Not usable on
  claude.ai in the browser or as an uploaded claude.ai skill: it needs local Python, the GPU, the
  photo folders and double-click launchers on your Mac.
- Homebrew (optional; installs ExifTool for captions in photo metadata)

## Folder layout

| Path | Content | In git? |
|---|---|---|
| `RUN Snap to Album.command` | Starts Claude Code in this folder with "create a photo album" | yes |
| `New photos/` | Photos waiting to be processed | no |
| `Albums/` | Finished albums (`*.html`), captioning launchers (`* – add captions.command`), `Photos with captions/` | no |
| `.claude/skills/snap-to-album/` | The Claude Code skill: `SKILL.md` (workflow) and `album-format.md` | yes |
| `system/scripts/`, `system/templates/` | The code | yes |
| `system/tests/run_tests.py` | Self-test: synthetic album page, loose print and back side run through the whole workflow in a temporary folder (no personal photos needed) | yes |
| `system/setup.sh`, `system/requirements.txt` | Installation | yes |
| `system/.venv/`, `system/models/` | Python environment and model weights (created by setup) | no |
| `system/config.json` | Your settings | no |
| `system/work/<album>/` | Working files per album; `system/work/captions.json`, `system/work/inventory.db` | no |
| `system/folder_version/<album>/` | Each album as a folder (HTML + WebP) — used by the captioning window | no |
| `system/used photos/` | Originals already in an album (moved from `New photos/`) | no |
| `system/test photo/` | The photo used for the first-run choice | no |

Nothing personal is ever part of the repository (see `.gitignore`).

## Installation

Claude runs `bash system/setup.sh` on the first run (after asking). By hand:

```bash
bash system/setup.sh
system/.venv/bin/python system/scripts/check_setup.py
```

It creates `system/.venv/` (NumPy, OpenCV, Pillow, PyTorch, GFPGAN, BasicSR, facexlib), downloads the
face-restoration weights (~350 MB) into `system/models/` and installs ExifTool via Homebrew if
available. GFPGAN, BasicSR and facexlib are installed from their official source packages with a
small, visible compatibility fix for Python 3.13+ (details in `THIRD_PARTY_NOTICES.md`).

## Self-test

```bash
system/.venv/bin/python system/tests/run_tests.py
```

Builds three synthetic snapshots (an album page with three prints, a loose print, the back of a
print), copies the scripts into a temporary folder and runs convert → detect → backs → enhance →
build → captioning window (over HTTP) → move_used → inventory there, plus unit tests of the pure
helpers. Takes about 10 s and touches nothing outside the temporary folder. Run it after any change
to the scripts — and before porting to another operating system.

## Workflow and scripts

All scripts: `system/.venv/bin/python system/scripts/<name>.py`, run from the project folder.

| Script | Purpose | Why this way |
|---|---|---|
| `check_setup.py` | Verifies libraries, model weights, ExifTool, GPU, settings | Clear diagnosis before the first run |
| `tool_test.py "<photo>"` | **Mandatory first-run step**: every enhancement option on one of your photos, comparison page with a slider | Restoration is a matter of taste and face restorers can alter features — you decide, on your own photo |
| `config.py [key value]` | Shows / changes settings | Every processing script refuses to run until the base enhancement is chosen |
| `convert.py <album>` | HEIC → full-size JPG + previews; lists snapshots in shooting order with time gaps | `sips` reads HEIC without extra software; the order reveals backs and close-ups |
| `detect_photos.py <album>` | Finds every photo on a page (or one print on a table), straightens it, numbered check sheet | OpenCV contour detection; for a single print every detector proposes and the largest plausible shape wins. Misses: `manual_corners.json` — rough boxes (`"approx"`) are snapped onto the real photo edges, see *Light backgrounds* below; `rotate.json` for sideways photos |
| `backs.py <album>` | Proposes back-side pairs | A back is recognized by content (plain paper with writing) **and** position (shot right after its front) — time alone is not reliable |
| `enhance.py <album>` | Applies the chosen look: colors → colorization → faces → upscaling | Separate logic for black-and-white, faded color prints, clippings and back sides |
| `ai_models.py` | Optional AI extras: Real-ESRGAN upscaling, ECCV16 colorization | Local PyTorch on the GPU; weights downloaded only when used |
| `build_album.py <album>` | Builds `Albums/<file>.html` (one self-contained offline file), the folder version, photos with captions, inventory | One file works offline everywhere; no server, no database, no internet |
| `make_launcher.py <album>` | Creates `Albums/<album> – add captions.command` | Nobody needs the Terminal to add captions |
| `caption_server.py <album>` | The captioning window (local web server on 127.0.0.1) | Every Enter saves straight into `captions.json`, the album file, the photo metadata and the inventory |
| `metadata.py <album>` | Writes caption, album name and date into JPG metadata (`Albums/Photos with captions/`) | Captions survive outside the album (Apple Photos, Finder) |
| `inventory.py` | Rebuilds the SQLite inventory and prints a summary | One place for captions, years, back sides, what is still uncaptioned |
| `photos_trips.py list` / `create <n> "<name>"` | **Experimental:** finds trips in the Apple Photos library (read-only database access, time gaps + GPS, home detection, Apple aesthetic score, coverage by existing albums) and creates albums in Photos via AppleScript, incl. airport photos ±30 h | Turns a huge digital library into albums in minutes; skips other people's shared-album photos (Photos forbids adding them) and hidden burst frames |
| `photos_album.py <n> "<title>" [--count 50]` | **Experimental:** best photos of a Photos trip (Apple aesthetic score + favorites, near-duplicates within 90 s removed, quota per day) → temporary export via Photos (downloads from iCloud) → 2400 px working copies → HTML album with one chapter per day, no restoration, captioning launcher | The digital counterpart of the paper-album workflow; raw exports are deleted, the Photos library is never changed |
| `photos_captions.py sync <album>` | **Experimental:** writes captions of a Photos-made album onto the original photos in the Photos app (Caption field, AppleScript); the captioning window does it automatically | Captions live on the originals — no re-import, no duplicates, iCloud sync |
| `move_used.py <album>` | Moves the album's originals to `system/used photos/` | `New photos/` only ever holds what is waiting |

The album content is described by `system/work/<album>/album.json` — see
`.claude/skills/snap-to-album/album-format.md`.

## Light backgrounds and touching photos

Automatic detection looks for photos that are **lighter than their surroundings** (a brightness
threshold). That is reliable on a dark album page. It fails when:

- prints lie on a **light wooden table** or the album has light pages — the white photo border is
  about as bright as the wood, so photo and table merge into one shape, or the photo is not found at
  all;
- photos **touch or overlap** on the page — they merge into one shape;
- a close-up shows a strip of dark page on one side and the table on another — choosing the method
  by background brightness picked the wrong one (now all methods propose and the largest
  plausible shape wins).

With prints photographed on a light table, about every second snapshot can need help.
Typing exact corners by eye is slow and never quite exact, so `manual_corners.json` accepts
**rough boxes**:

```json
{"IMG_0012": {"approx": [[120, 80, 760, 590], [[800, 60], [1500, 90], [1490, 610], [790, 580]]]}}
```

(1600 px preview coordinates; a box `[x0, y0, x1, y1]` or four corners per photo). `snap_corners`
then moves and tilts each edge within ±3 % onto the strongest brightness step — the real paper
edge — and intersects the four edges, so the crop is straight and exact even if the box was a few
pixels off. Claude reads the boxes from a preview with a 10 % grid drawn over it.

Limits, found while building it: the rough box has to be closer to the paper edge than to the
picture edge inside a white border (≈1–2 % off is fine) — otherwise the stronger picture edge wins
and the white border is cut off. Preferring the "outermost strong edge" instead was tried and
rejected: on real pages it jumped to an overlapping neighbour or the page edge.

**Tried and not included: Segment Anything (SAM).** Meta's segmentation model, run locally, sounded
like the fix. On album photos it was not: a point in the middle of a print selected a sweater or a
face rather than the print, a box around the whole snapshot returned the table or a face, and with
an accurate box it only matched what `snap_corners` already does — while adding a 375 MB download
and (on Apple GPUs) a crash, because its automatic mode needs float64 numbers that Metal does not
support. Rough boxes + edge snapping are smaller, faster and predictable.

**Tip for photographing:** a dark, plain background (a black cloth, the dark album page itself)
makes automatic detection work almost every time.

## Enhancement options

Chosen on the first run, changeable any time (`config.py enhancement …`, then `enhance.py` and
`build_album.py` again).

| Option | What it does |
|---|---|
| `none` | Crop and straighten only |
| `colors` | + automatic color and contrast restoration (faded colors, yellowed black-and-white) — OpenCV, no neural network |
| `colors+faces50` | + gentle face restoration (GFPGAN v1.4 mixed 50 % with the original, so faces keep their real features) |
| `colors+faces100` | + full face restoration |

Face restoration works on a copy of at most 2400 px: on a full-resolution phone shot of a class
photo (30 faces, 4000+ px) it took about a minute per photo, at 2400 px a few seconds. Only the
change it makes is enlarged back and added to the full-size photo, so everything that is not a face
keeps its full resolution.

**Optional AI extras** (off by default, also shown on the test photo):

| Setting | What it does | Keep in mind |
|---|---|---|
| `colorize bw` | Black-and-white photos get colors (ECCV16 model, Zhang, Isola & Efros) | Colors are guessed: skin, sky and grass are usually plausible, clothes and objects are not known |
| `upscale 2x` / `4x` | Upscaling with Real-ESRGAN (general x4 v3) | Sharpens, but invents fine texture (skin, hair, paper grain) that was never in the photo |

A note from real use: on old family prints, a phone photo usually has enough resolution and the
upscaler's invented texture can look like fine cracks; colorization guesses colors. That is why both
are opt-in. Some people love them — try them on your test photo.

Clippings and back sides always get only a gentle treatment (no AI extras).

## Settings for different ways of working

| Setting | Values | Use it when |
|---|---|---|
| `time_source` | `auto` (default) · `exif` · `file` · `name` | How the order and time of snapshots is determined: `exif` = time stored by the phone/camera; `file` = file date (scanners, edited/exported files); `name` = file-name order only (`scan_001…`); `auto` = EXIF, otherwise file date |
| `back_max_gap` | seconds, default `60`; `0` = ignore time | Max. time between a photo and its back side. `0` if you scanned or shot the backs later — then only the order counts |
| `metadata_date` | `year` (default) · `capture` · `none` | Date written into `Photos with captions`: the year the photo shows (from captions/chapters — Apple Photos then sorts by family history), when you took the snapshot, or none |
| `view_photos` | `yes` · `no` | Whether Claude may look at photo previews (see Privacy) |

`config.py` without arguments lists everything with current values.

## Safety nets

- **Unique snapshot ids.** Every original gets an id (normally its file name) in
  `system/work/snapshots.json`. If the name is already taken by a different photo — iPhone numbering
  restarts after IMG_9999, a second phone, an edited copy with the same number — the new one becomes
  `IMG_0012-2`. Captions, crops and the inventory never mix them up.
- **Originals are never overwritten.** `move_used.py` adds " (2)" when `system/used photos/` already
  holds a file with the same name.
- **Clippings and back sides stay gentle.** Marked in `clippings.json` / `backs.json`; the build
  restores the gentle version if a full AI-processed one exists.
- **Captions are saved one at a time** (file lock), so quick successive Enters — or two captioning
  windows open at once — never overwrite each other. Each album uses its own port.
- **A changed look is applied automatically.** Every processed photo carries a note of the settings
  it was made with (`enhanced/<id>.cfg`); after you change the enhancement, colorize or upscale
  setting, the next build processes the affected photos again — no separate step to remember.
- **Pinned dependencies.** `requirements.txt` pins major versions, so a new major release of
  NumPy, OpenCV or PyTorch cannot break a fresh installation.
- **Deleting a caption** in the window stores an empty caption, which overrides one Claude wrote.
- **Moving photos between albums** only changes `album.json`; the build finds each photo in
  whichever album folder holds it and stops with a clear message if an id does not exist.
- **Downloads are verified** against the official SHA-256 checksums; the captioning window accepts
  saves only from its own page.

## How years are found

The year of a photo is the first year in its caption (the current year and later are ignored — a
caption like "still there today (2026)" means today), otherwise the chapter's year or date,
otherwise the only year in the album title.

## Privacy in detail

- **All image processing runs locally**: cropping and colors on the CPU (OpenCV); face restoration and
  the AI extras on the GPU via PyTorch (Apple Silicon: Metal/MPS, NVIDIA: CUDA, otherwise CPU).
- The scripts **never upload photos** anywhere and contain no telemetry. The captioning window is a
  web server bound to `127.0.0.1` — reachable only from your own Mac.
- Network use is limited to **downloading software and weights**: `setup.sh` (PyPI, the official
  GFPGAN/facexlib GitHub releases, Homebrew) and, on first use of the AI extras, the Real-ESRGAN
  GitHub release and the colorization authors' official download.
- **Apple Photos:** a read-only snapshot of the Photos database is used (cloned instantly into a
  temporary folder and deleted afterwards — the live library is never locked or changed). Days and
  times are the local time where each photo was taken. The database layout is not documented by
  Apple and may change with macOS updates; the scripts find the album table by its columns and
  report clearly when something cannot be read. Only a summary (dates,
  Apple's place names, numbers of photos) is shown — and sent to Anthropic when Claude runs it.
- **Claude itself runs in the cloud.** When Claude opens a photo preview (to read handwriting, check a
  crop, propose chapters), that image is sent to Anthropic as part of the conversation. With
  `view_photos no`, Claude never opens images.

## Publishing (not included)

The project creates offline archives for personal use and never publishes anything. If a user
decides to host an album, `system/folder_version/<album>/` is a static site (pages carry
`noindex`); hosting is a separate, user-initiated step — always password-protected. See *Fair use*
in `README.md`.

## Licenses

MIT for this project. Third-party components, model weights, training data and the compatibility
fixes are documented in `THIRD_PARTY_NOTICES.md`.
