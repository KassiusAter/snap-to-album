"""Verifies the installation: libraries, model weights, exiftool, compute device."""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

ok = True
for mod in ("numpy", "cv2", "PIL", "torch", "gfpgan", "facexlib"):
    try:
        __import__(mod)
        print(f"  ok   {mod}")
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"  FAIL {mod}: {e}")
for f in ("GFPGANv1.4.pth", "gfpgan/weights/detection_Resnet50_Final.pth", "gfpgan/weights/parsing_parsenet.pth"):
    there = os.path.exists(os.path.join(common.MODELS, f))
    ok &= there
    print(f"  {'ok  ' if there else 'MISSING'} models/{f}")
print(f"  {'ok  ' if shutil.which('exiftool') else 'missing (optional)'} exiftool")
try:
    print(f"  compute device for face restoration: {common.device()}")
except Exception as e:  # noqa: BLE001
    print(f"  compute device: unknown ({e})")
for f, what in (("realesr-general-x4v3.pth", "upscaling"), ("colorization_eccv16.pth", "colorization")):
    there = os.path.exists(os.path.join(common.MODELS, f))
    print(f"  {'ok  ' if there else 'not downloaded (optional, fetched on first use)'} models/{f} — AI add-on: {what}")
cfg = common.load_config()
print(f"  enhancement tool: {cfg.get('enhancement') or 'NOT CHOSEN YET — first-run step required'}")
print(f"  AI add-ons: colorize {cfg['colorize']}, upscale {cfg['upscale']}; time source {cfg['time_source']}")
sys.exit(0 if ok else 1)
