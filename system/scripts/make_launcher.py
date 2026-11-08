"""Creates the double-click captioning launcher for an album, right next to the album file:

  system/.venv/bin/python system/scripts/make_launcher.py <album>
  → Albums/<album file name> – add captions.command

Double-click it: a small Terminal window opens and the album opens in the browser with a text
field under every photo. Type what you know, press Enter. Close the Terminal window when done.
"""
import os
import shlex
import stat
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

name = sys.argv[1]
a = common.load_album(name)
title = os.path.splitext(a["output_file"])[0]
os.makedirs(common.ALBUMS, exist_ok=True)
path = os.path.join(common.ALBUMS, f"{title} – add captions.command")
# album names and titles are quoted, so no character in them can ever run as a command
safe_title = title.replace("\n", " ")
with open(path, "w", encoding="utf-8") as f:
    f.write(f"""#!/bin/zsh
# Double-click: opens an album in your browser, ready for captions.
# Every caption is saved when you press Enter. To finish, close this window.
cd "$(dirname "$0")/.." || exit 1
printf '\\e[8;6;72t'
echo {shlex.quote(f"Adding captions to “{safe_title}”.")}
echo "Type under each photo and press Enter. When you are done, just close this window."
echo
exec system/.venv/bin/python system/scripts/caption_server.py {shlex.quote(name)}
""")
os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
print(path)
