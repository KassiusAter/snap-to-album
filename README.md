# Snap to Album

**Save and restore your old family albums — no tech skills needed.**

Photograph the album pages with your phone, drop the photos into `New photos`, double-click
**RUN Snap to Album** — then caption them together with your grandparents.

Each album becomes one file that opens in any browser, even offline: chapters on a timeline, the
handwriting from the pages, the back of each photo one click away. Copy it to a USB stick or send
it to the family.

**You choose the look.** Before anything is processed, Claude shows one of your photos in every
version side by side: just cropped · colors fixed · faces gently or fully restored, plus optional
colorizing and enlarging. The unretouched photo always stays one click away.

**Captioning is like writing on the back of a photo.** Double-click, type *"Aunt Mary at the lake,
summer 1962"*, press Enter. The caption is saved in the album and inside the photo file, so it
travels with the photo wherever you copy it.

**Already use Apple Photos?** Claude can find your trips and turn them into albums — see
[below](#albums-from-apple-photos-experimental).

Claude does all the technical work; you just answer simple questions.

> **Needs a Mac and Claude Code** (desktop app or Terminal) — not claude.ai in the browser, because
> the photos are processed on your own computer. Windows and Linux versions are in the works.

## How it works

1. **Download** this project (green **Code** button → **Download ZIP**) and unzip it anywhere.
2. **Photograph** the album pages with any phone or camera, or scan them:
   - whole pages, straight from above, no flash, no glare
   - a dark, plain background works best
   - tiny photo? add a close-up right after the page
   - writing on the back? photograph the back right after the front
3. **Copy** the photos into **`New photos`** (HEIC, JPG, PNG, TIFF).
4. **Double-click `RUN Snap to Album`.** The first time, macOS may block it — right-click it and
   choose Open. In the Claude desktop app, open this folder and type **create a photo album**.
5. **First time only:** Claude sets everything up (it asks before downloading about 1.5 GB) and
   lets you choose the look.
6. **Caption:** in `Albums`, double-click **`… – add captions`**, type and press Enter. Claude can
   then sort the photos by your captions, keeping them in chronological order.

## Albums from Apple Photos *(experimental)*

Ask Claude to **"find trips in my Photos app"**. It finds your trips by time and place and shows
which ones have no album yet — *"Lisbon, 12–15 May 2019, 420 photos — no album yet"*. For each trip
you can get:

- **an album right in the Photos app** — all photos of the trip, including the airport on the way;
  nothing is copied or moved;
- **an offline album for captioning** — the best shots picked by Apple's quality score. Captions
  you type also go onto the original photos in Photos, synced by iCloud.

Claude opens your Photos library only when you ask, and macOS asks for permission the first time.

## What you see in the folder

```
Snap to Album/
  RUN Snap to Album.command  ← double-click to start
  New photos/                ← put your photos here
  Albums/                    ← your finished albums
     1950–1959 Grandma.html                     the album — open it in any browser
     1950–1959 Grandma – add captions.command   double-click to type captions
     Photos with captions/                      photo files carrying their captions
  system/                    ← the machinery — no need to open it
```

## Private and offline

- Photos are processed **on your Mac**. Nothing is uploaded or published; the internet is used only
  once, to download the tools. There is no "share online" button, on purpose.
- **One honest note:** if you allow it, Claude looks at small previews to read handwriting and check
  its work — those previews are sent to Anthropic like any picture you show Claude. You decide on
  the first run; if you say no, Claude asks you instead.

## Fair use

- **Photos have authors** — a family member or a studio. Sharing in the family is fine, publishing is not.
- **Newspaper clippings and postcards** belong to their publishers.
- **People in the photos** have a right to privacy — ask before putting them online, and use a password.
- **Restored is not original.** The paper album stays the real record.

## More

- **`TECHNICAL.md`** — how it works inside, all settings, privacy in detail.
- **`THIRD_PARTY_NOTICES.md`** — open-source tools used, their licenses, commercial use.
- License: MIT. Thanks to OpenCV, PyTorch, GFPGAN, BasicSR, facexlib, Real-ESRGAN,
  *Colorful Image Colorization* (Zhang, Isola & Efros) and ExifTool.
