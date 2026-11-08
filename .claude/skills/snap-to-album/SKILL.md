---
name: snap-to-album
description: Snap to Album — turns phone photos (iPhone, Android), camera shots or scans of old paper photo albums and loose prints into a private offline archive, with no tech skills needed. It also works with the Apple Photos app on the Mac: it finds trips by time and place, picks the best shots by Photos' own aesthetic (quality) score and turns them into offline HTML albums for captioning and private sharing — or creates albums for them right in Photos. One self-contained HTML file per album (chapters, timeline, restored photos, back sides). The user picks the restoration on one of their own photos first, comparing every option side by side (crop only, color fix, gentle or full face restoration, optional AI colorization and upscaling) — nothing is enhanced without their choice. Captioning is as simple as writing on the back of a photo: grandparents double-click a launcher, type who is who under each photo and press Enter — each caption is saved both in the album and inside the photo file's own metadata, so the photo keeps its story anywhere (Apple Photos, other computers). Plus an inventory of all photos. The user never touches the Terminal — Claude does every technical step. Use when the user says "create a photo album", "make a photo album", "digitize my photo album", "continue the photo album", "add captions", "snap to album", "find trips in my Photos", "make an album from my Photos", "make albums from my Photos", or the same in any other language.
---

# Snap to Album

Two sources, one result — a private offline HTML album with a captioning window:
- **Paper albums:** photographs of album pages and loose prints (sections 0–5).
- **Apple Photos app:** digital photos already on the Mac — trips found by time and GPS, the best
  shots picked by the Photos app's own aesthetic score, or albums created right in the Apple Photos
  app (section 6).

The user photographs album pages with a phone or camera (or scans them), drops the photos into
`New photos/`, double-clicks
`RUN Snap to Album`, and you turn them into a finished album. Then the family — typically sitting
together with the grandparents, who know who is who — adds captions by double-clicking a launcher.
Every caption lands in two places at once: the album file and the photo's own metadata.

## How to talk to the user

**Assume the user has no technical knowledge.**
- Do every technical step yourself: installation, scripts, settings, JSON files. Never ask the user
  to open the Terminal, type a command or edit a file.
- Ask only simple, plain-language questions with clear choices (AskUserQuestion). No jargon: say
  "how strongly should faces be touched up", not "GFPGAN blend weight".
- Tell them what is happening in one short sentence when something takes a while (installation,
  enhancing many photos), and what they get at the end.
- Where something needs their eyes (choosing the look on the test photo, a crop you are unsure
  about), open the page/picture for them (`open <file>`) and describe exactly what to look at.

All commands below run from the project folder: `system/.venv/bin/python system/scripts/<script>.py`
(written `PY <script>` below).

## 0. First run (check every time, before anything else)

1. **Installation.** If `system/.venv/` or `system/models/GFPGANv1.4.pth` is missing: tell the user
   that a one-time setup will download about 1.5 GB (the photo tools and the face model) and take a
   few minutes; after they agree, run `bash system/setup.sh` yourself and report when it is done.
   `PY check_setup` verifies it.
2. **May you look at the photos?** If `system/config.json` has no `view_photos`, ask:
   "To read the handwriting in the album and check that photos are cut out correctly, I can look at
   small previews of your photos. Those previews are then sent to Anthropic as part of our
   conversation — the photo processing itself stays on your Mac. May I look at them?"
   Save with `PY config view_photos yes|no` and respect it for the whole project. With `no`, never
   open an image; show the user the overview pictures instead and let them tell you what they see.
3. **MANDATORY: choose the look.** If `system/config.json` has no `enhancement`, nothing else may run
   (the scripts refuse anyway). Pick one photo from `New photos/` with a face (ask the user which
   one if you may not look), run `PY tool_test "New photos/<file>"` — it opens a comparison page —
   and tell the user how to use it (drag the slider, click the buttons). Then ask in plain words:
   - base look (one, required): *crop only* (`none`) · *fix colors and contrast* (`colors`) ·
     *+ gently touch up faces* (`colors+faces50`) · *+ strongly touch up faces* (`colors+faces100`)
   - optional extras (off unless they want them): *add colors to black-and-white photos* (`colorize bw`,
     colors are a guess) · *make photos larger and sharper* (`upscale 2x`, invents fine detail)
   Save with `PY config enhancement <option>` (and `PY config colorize bw`, `PY config upscale 2x`).
   **Never choose for the user.** Mention that face touch-ups can change how people look, which is
   why the gentle option exists. They can change it any time — then re-run `enhance` and `build_album`.

## 1. From photos to crops

1. Ask for a working title of the album; derive a short folder-safe name yourself (e.g. `grandma_1950s`).
2. `PY convert <album>` → JPG copies and previews; it prints the snapshots in shooting order with the
   seconds between them. Check the order makes sense; if not, adapt the settings to how the user
   worked (ask in plain words if unclear):
   - phone or camera, back of a photo shot right after its front → defaults
   - times missing or all the same (copied/edited files) → `PY config time_source file` or `name`
   - scanner with numbered files → `time_source name`, `back_max_gap 0`
   - backs photographed later or in a batch → `back_max_gap 0`, pair them with the user
3. Classify every snapshot (from previews if allowed, otherwise ask): **album page**, **single photo**,
   **back side** (writing on the back of the photo shot just before), **close-up** (sharper shot of one
   photo that is also on a page), or **skip**. If a name was already used by another photo,
   `convert` gives the snapshot an id like `IMG_0012-2` — always use the ids it prints.
4. `PY detect_photos <album>` cuts out and straightens every photo; check
   `system/work/<album>/check/_overview.jpg`. Fix misses in `manual_corners.json` (corners in the
   1600 px preview, or `"whole"` / `"single"`) and sideways photos in `rotate.json`
   (`{"IMG_0004_1": 90}`, clockwise); re-run for those snapshots.
5. Newspaper clippings, cartoons, postcards: list their photo ids in
   `system/work/<album>/clippings.json` (`["IMG_0010_3"]`) **before enhancing**, so they get only the
   gentle treatment (the build also re-checks this).
6. `PY backs <album>` proposes back-side pairs. Check them, write confirmed pairs to `backs.json`
   (`{"<back id>": "<front id>"}`) and copy the writing on the back into the front's caption.
7. Close-ups: in `album.json` → `"use_closeup": {"IMG_0010_2": "IMG_0011_1"}`.
8. `PY enhance <album>` applies the chosen look (on the Mac's GPU when available).

## 2. Chapters and the album

Read handwritten captions on the pages (if allowed), use dates and shooting order, and **propose**
chapters in chronological order — in plain words, as a short list. After the user agrees, write
`system/work/<album>/album.json` (format: `album-format.md` next to this file). Start `output_file`
with the year(s), e.g. `"1950–1959 Grandma.html"`, so albums sort by time. Before the first build,
ask whether photos copied with captions should carry the year they show (default — Apple Photos then
sorts them by family history), the date the snapshot was taken, or no date (`PY config metadata_date year|capture|none`).

`PY build_album <album>` → `Albums/<output_file>`: one offline HTML file with all photos inside — the
file for the family. Also refreshes `Albums/Photos with captions/` and the inventory.

## 3. Captions — always part of the result

Old albums rarely have captions, and the grandparents know who is who — captioning must be as easy
for them as writing on the back of a photo. **After every build, run `PY make_launcher <album>`** →
`Albums/<album> – add captions.command`, and suggest doing it together with parents or grandparents.
Explain it like this: "Next to your album there is a file '… – add captions'. Double-click it (the
very first time: right-click → Open). Your album opens in the browser with a box under every photo.
Type whatever you know — who, where, when, a year — and press Enter. That's all: no saving, no menus.
Each caption is stored in the album and also inside the photo file itself, so the photo keeps it
when you copy it to Apple Photos or anywhere else. Close the small black window when you are done."
Each Enter saves to `system/work/captions.json`, the album file, the photo's metadata and the
inventory — no rebuild needed. One free-text box per photo, on purpose. Emptying a box and pressing
Enter deletes the caption for good (also one you wrote into `album.json`).

## 4. Re-organizing by captions

When captions are in, read `system/work/captions.json` or the inventory
(`sqlite3 system/work/inventory.db "select album, id, year, caption from photos"`). Years are taken
from the captions automatically (the current year is ignored — it means "today"). Propose a clearer
grouping — also moving photos between albums — that **keeps chronological order**; photos without a
date stay where they were in the paper album. After approval, edit the `album.json` files (to move a
photo, list its id in the other album and remove it from the first — files stay where they are),
rebuild both albums and re-create the captioning launchers.

## 5. Finish

`PY move_used <album>` moves the originals from `New photos/` to `system/used photos/`, so
`New photos/` only holds what is still waiting. Tell the user where their album and the captioning
launcher are, in one or two sentences.

## 6. Bonus (experimental): albums from the Apple Photos library

**Only when the user explicitly asks for it** ("find trips in my Photos", "make an album from my
Photos", …). Never open, read or scan the Photos library on your own — not on "create a photo album",
not to check something, not during the first run. If `New photos/` is empty and the user only said
"create a photo album", you may *ask* whether they want to use photos from the Photos app instead;
touch the library only after they say yes.

For digital photos already in the Photos app (macOS). Nothing is copied, moved or deleted — an
album in Photos only refers to photos that are already there.

1. `PY photos_trips list` reads the Photos database **read-only**, finds trips (time gaps + GPS,
   joined over consecutive days away from home), scores them and shows which are **not yet in any
   album**, numbered. Present the best ones in plain words, e.g. "Lisbon, 12–15 May 2019, 420
   photos — no album yet". It also shows trips that are only partly in an album.
2. The user picks trips and names. Suggest names in the style of their existing albums
   (typically "Place year"; look at existing album names in the list output if unsure).
3. `PY photos_trips create <number> "<name>"` creates the album in Photos with all photos of the
   trip, plus photos taken at airports up to 30 h before/after (departure and arrival). Use
   `--dry-run` first if unsure. It refuses if an album with that name already exists.
4. Report the result in one line per album. Mention the two automatic skips when they occur:
   - photos from **other people's shared albums** — Photos does not allow adding them to the
     user's own albums; they can save them to their library first ("Add to Library") and you add
     them afterwards
   - **hidden burst frames** — nothing is missing, the burst's key photo is in the album
Privacy: only the summary (dates, Apple's place names, counts) reaches the conversation, no photos.
macOS may ask once for permission to control Photos, or for Full Disk Access to read the library.

5. **HTML album for captioning and sharing (experimental):** `PY photos_album <number> "<title>"
   [--count 50]` picks the best photos of the trip (Apple's aesthetic score + favorites, no
   near-duplicates within 90 s, spread over all days, own photos only), lets Photos export them
   (downloads from iCloud if needed — can take a few minutes; tell the user), keeps 2400 px working
   copies, deletes the raw exports and builds a normal Snap to Album: one chapter per day titled with
   Apple's place names, no cropping or restoration, plus the captioning launcher. Suggest 30–60
   photos for a weekend, more for longer trips. Ask the user to look at the result.
   Captions typed in the captioning window are also written onto the original photos in the Photos
   app (their Caption field, via `photos_captions.py`) a moment after each Enter; existing Photos
   captions are pre-filled. `PY photos_captions sync <album>` sends all captions at once. Mention this
   to the user — it is the main advantage: grandparents caption in the browser, the captions end up
   in Photos on all their devices. Never re-import photos into Photos (that would create duplicates).

## Rules

- The Apple Photos library is accessed **only on the user's explicit request** (section 6).

- The project makes **offline archives for personal and family use**. It never uploads or publishes
  anything, and you do not offer publishing on your own.
- Only if the user explicitly asks to put an album online: say this is not part of the project, remind
  them briefly that photos have authors, newspaper clippings belong to their publishers and people in
  the photos have a right to privacy (README → *Fair use*), and then — as a separate task the user
  confirms — help them host the album's folder version (`system/folder_version/<folder>/`, a static
  site whose pages carry `noindex`), always password-protected. Never upload anything without the
  user's explicit go-ahead.
- If the user wants to use the project commercially, point them to `THIRD_PARTY_NOTICES.md`.
- Originals are never modified or deleted. The captioning window listens on 127.0.0.1 only.
- The user approves the look, the chapters, uncertain back-side pairs and every re-organization.
- If a script says "First-run step missing", go back to step 0.3.
- Technical reference for everything: `TECHNICAL.md` in the project folder.
