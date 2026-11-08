"""Shows or changes the project settings (config.json).

  system/.venv/bin/python system/scripts/config.py                 show all settings, their values and options
  system/.venv/bin/python system/scripts/config.py <key> <value>   change one setting

Settings:
  enhancement    none | colors | colors+faces50 | colors+faces100   (mandatory, first-run step)
  colorize       off | bw            AI colorization of black-and-white photos
  upscale        off | 2x | 4x       AI upscaling
  view_photos    yes | no            may Claude open photo previews
  time_source    auto | exif | file | name
  back_max_gap   seconds (0 = ignore time when pairing back sides)
  metadata_date  year | capture | none
After changing enhancement, colorize or upscale, re-run enhance.py and build_album.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

cfg = common.load_config()
args = sys.argv[1:]
if not args:
    for key, (allowed, _, meaning) in common.SETTINGS.items():
        print(f"{key:14} = {cfg.get(key, '(not chosen)')}")
        print(f"{'':17}{meaning}")
        if allowed:
            print(f"{'':17}options: {' | '.join(allowed)}")
    sys.exit()
if len(args) != 2 or args[0] not in common.SETTINGS:
    sys.exit(f"Usage: config.py <key> <value>; keys: {', '.join(common.SETTINGS)}")
key, value = args
allowed = common.SETTINGS[key][0]
if allowed is None:
    if not value.isdigit():
        sys.exit(f"{key} must be a whole number")
    value = int(value)
elif value not in allowed:
    sys.exit(f"Unknown value '{value}' for {key}. Choose one of: {', '.join(allowed)}")
saved = {k: v for k, v in cfg.items()}
saved[key] = value
common.save_config(saved)
print(f"{key} = {value}")
