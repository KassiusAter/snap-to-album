# album.json format

`system/work/<album>/album.json` describes one album. Claude writes it after the user approves the
chapters; it can be edited by hand at any time (then Claude rebuilds the album).

```json
{
  "title": "Grandma",
  "subtitle": "1950–1959",
  "intro": "The album Grandma kept from her wedding to the birth of her second child.",
  "lang": "en",
  "output_file": "1950–1959 Grandma.html",
  "folder": "grandma_1950s",
  "caption_label": "Written in the album",
  "chapters": [
    {
      "group": 1952,
      "title": "The wedding",
      "date": "14 June 1952",
      "album_caption": "Our wedding day – 14. 6. 1952",
      "featured": ["IMG_0102_1"],
      "pages": ["IMG_0102", "IMG_0103"]
    },
    {
      "group": "Holidays",
      "title": "At the sea",
      "featured": ["IMG_0110_1"],
      "grid": ["IMG_0111_1", "IMG_0112_1"]
    }
  ],
  "clippings": ["IMG_0103_4"],
  "captions": {"IMG_0102_1": "Grandma and Grandpa in front of the church"},
  "use_closeup": {"IMG_0103_2": "IMG_0104_1"}
}
```

| Field | Meaning |
|---|---|
| `title`, `subtitle`, `intro` | Cover of the album and the menu heading |
| `lang` | Language code of the page (`en`, `de`, `cs`, …) |
| `output_file` | Name of the finished file in `Albums/` — start it with the year(s) so albums sort chronologically |
| `folder` | Folder name of the album's folder version and of the metadata copies |
| `caption_label` | Small label above the handwritten page caption |
| `chapters[].group` | Year (number) or short label; chapters with the same group share a menu heading. A numeric year also dates its photos |
| `chapters[].title`, `date` | Chapter heading and free-text date |
| `chapters[].album_caption` | Handwritten caption from the page, verbatim (shown as chalk on a board) |
| `chapters[].featured` | Best photos, shown large |
| `chapters[].pages` | Album pages (snapshot ids) in album order; their remaining photos follow in a grid in page order, plus a "whole page" button |
| `chapters[].grid` | Further photos (for loose prints that are not on a page) |
| `clippings` | Newspaper clippings, drawings: gentle processing, no face restoration, no white border |
| `captions` | Captions written by Claude (e.g. from the back of a photo). Captions typed in the browser (`system/work/captions.json`) take precedence |
| `use_closeup` | A page crop replaced by a sharper close-up of the same photo |

Photo id = `<snapshot>_<n>`: photo *n* on snapshot *IMG_0102*, numbered top-to-bottom, left-to-right.
Back sides are not listed here; they come from `backs.json` and appear as a "back of photo" button.
