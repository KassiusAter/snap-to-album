# Snap to Album

**Your old family albums, saved — no tech skills needed.**

Photograph the pages with your phone → drop the photos into a folder → double-click
**RUN Snap to Album** → sit down with your grandparents and caption the photos together.

You get a **private offline archive**: one file per album that opens in any web browser, without
internet, and that you can copy to a USB stick or send to your family. Chapters on a timeline,
photos gently restored, the handwriting from the pages, the back of a photo one click away.

**Captions as easy as writing on the back of a photo.** Your grandmother knows who is who — and she
does not need to learn anything: double-click, the album opens, there is a box under every photo,
she types *"Aunt Mary at the lake, summer 1962"* and presses Enter. That is all. Each caption is
saved twice at once: **in the album** and **inside the photo file itself** (its metadata), so the
photo keeps its story even when it is copied to Apple Photos, another computer or a USB stick.

Claude does all the technical work. You only answer simple questions.

> **You need a Mac and Claude Code** — either the Claude desktop app or Claude Code in the Terminal.
> It does not work on claude.ai in the browser: your photos are processed on your own computer,
> which a web page cannot do.

## How it works

1. **Download** this project (green **Code** button → **Download ZIP**, then unzip) and put the
   folder wherever you like.
2. **Photograph** your album pages — with any phone (iPhone, Android) or camera; a scanner works
   too. Whole pages, straight from above, no flash, no glare. Tiny or precious photo? Add a close-up right after the page. Loose photo with writing on
   the back? Photograph the front, then straight away the back.
3. **Drop** the photos into the **`New photos`** folder — AirDrop, a cable, a memory card or your
   cloud folder, whatever you normally use. iPhone HEIC, JPG, PNG and TIFF are all fine.
4. **Double-click `RUN Snap to Album`.** Claude starts and creates your album.
   *The very first time macOS may ask whether to open it: right-click → Open.*
   Prefer the Claude desktop app? Open this folder there and type **create a photo album**.
5. **First time only:** Claude sets everything up by itself (it asks before downloading about
   1.5 GB) and shows you one of your photos in several versions — *you* choose the look you like.
6. **Caption the photos — ideally together with your parents or grandparents.** Next to your album
   in the **`Albums`** folder you will find **`… – add captions`**. Double-click it: the album opens
   with a box under every photo. Type what you know — who, where, when — and press Enter. No saving,
   no menus: every caption goes straight into the album and into the photo file's own data.
   Afterwards Claude can sort the photos by your captions, keeping the time order.

## What you see in the folder

```
Snap to Album/
  RUN Snap to Album.command  ← double-click to start
  New photos/                ← put your photos here
  Albums/                    ← your finished albums
     1950–1959 Grandma.html                     the album — open it in any browser
     1950–1959 Grandma – add captions.command   double-click to type captions
     Photos with captions/                      the photos as files, each carrying its caption (for Apple Photos)
  system/                    ← the machinery — no need to open it
```

## Your photos stay on your Mac

- Your photos are processed **on your own computer** (its processor and graphics chip). Nothing is
  uploaded to any cloud, website or photo service, and nothing is published.
- The internet is used only to download the tools once.
- **One honest note:** Claude is an online assistant. If you allow it, Claude looks at small previews
  of your photos to read handwriting and check its work — those previews are then sent to Anthropic
  as part of your conversation, like any picture you show Claude. You decide on the first run; if you
  say no, Claude never opens a photo and simply asks you instead.

## Offline by design

Snap to Album makes **offline archives for personal and family use**. It has no "share online"
button — on purpose. If you ever want to put an album on the internet, that is a separate step you
would take yourself (Claude can help if you ask); please read the next section first.

## Fair use of your albums

- **Photos have authors.** A photo belongs to whoever took it — often a family member, sometimes a
  studio (weddings, school photos). Sharing in the family is fine; publishing openly is different.
- **Newspaper clippings, cartoons and postcards** in old albums belong to their publishers. They stay
  in your album because they are part of its story — but they are not yours to publish.
- **People in the photos** have a right to privacy. Ask before putting recognizable people online,
  and keep anything you share behind a password.
- **Restored is not original.** Touched-up faces, added colors or enlargement change a photo. The album
  always keeps the unretouched version one click away, and the paper album stays the real record.

## Need more?

- **`TECHNICAL.md`** — how it works inside: every script and why, all settings (scanners, other
  cameras, dates), the optional AI extras, privacy in detail, requirements.
- **`THIRD_PARTY_NOTICES.md`** — the open-source tools this project builds on, their licenses, and a
  note on commercial use.
- License: MIT (`LICENSE`). Thank you to the authors of OpenCV, PyTorch, GFPGAN, BasicSR, facexlib,
  Real-ESRGAN, *Colorful Image Colorization* (Zhang, Isola & Efros) and ExifTool.
