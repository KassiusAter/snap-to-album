#!/bin/bash
# One-time setup: Python environment + face-restoration model weights.
# Everything is installed into this folder (.venv/ and models/); nothing system-wide
# except exiftool (via Homebrew), which writes captions into photo metadata.
# Tested on macOS (Apple Silicon) with Python 3.14.
set -e
cd "$(dirname "$0")"

if [[ "$(uname)" != "Darwin" ]]; then
  echo "This project currently targets macOS (it uses the built-in 'sips' tool to read iPhone HEIC photos)."
  exit 1
fi

PY="${PYTHON:-python3}"
echo "== Python environment (.venv) using $($PY --version)"
"$PY" -m venv .venv
PIP=".venv/bin/pip"
$PIP install --quiet --upgrade pip setuptools wheel
$PIP install --quiet -r requirements.txt

# GFPGAN and its helpers (basicsr, facexlib) only ship source packages whose setup.py
# fails on Python >= 3.13 (it reads __version__ via exec + locals()). We download the
# official source archives from PyPI, fix that one function, and install them.
echo "== GFPGAN, basicsr, facexlib (source packages, with a small compatibility fix)"
BUILD=$(mktemp -d)
for pkg in basicsr/1.4.2 facexlib/0.3.0 gfpgan/1.3.8; do
  url=$(curl -fsSL "https://pypi.org/pypi/$pkg/json" | .venv/bin/python -c \
    "import json, sys; print(next(u['url'] for u in json.load(sys.stdin)['urls'] if u['packagetype'] == 'sdist'))")
  curl -fsSL "$url" | tar xz -C "$BUILD"
done
for dir in "$BUILD"/*/; do
  .venv/bin/python - "$dir/setup.py" <<'EOF'
import sys
p = sys.argv[1]
s = open(p).read()
s = s.replace("exec(compile(f.read(), version_file, 'exec'))",
              "_ns = {}\n        exec(compile(f.read(), version_file, 'exec'), _ns)")
s = s.replace("return locals()['__version__']", "return _ns['__version__']")
open(p, "w").write(s)
EOF
  $PIP install --quiet --no-build-isolation --no-deps "$dir"
done
$PIP install --quiet basicsr==1.4.2 facexlib==0.3.0 gfpgan==1.3.8   # their own dependencies
rm -rf "$BUILD"

# basicsr imports a torchvision module that was renamed in torchvision 0.17 (one-line fix in .venv).
DEG=$(.venv/bin/python -c "import importlib.util, os; print(os.path.join(os.path.dirname(importlib.util.find_spec('basicsr').origin), 'data', 'degradations.py'))")
sed -i '' 's/torchvision\.transforms\.functional_tensor/torchvision.transforms.functional/' "$DEG"

echo "== Model weights (downloaded once from the official GitHub releases, ~350 MB)"
echo "   (the optional AI add-ons — upscaling, colorization — download their weights only if you try or choose them)"
mkdir -p models/gfpgan/weights
# download once, then check the file against its official SHA-256 checksum
get() {
  if [[ ! -s "$2" ]]; then curl -fL --progress-bar -o "$2.part" "$1" && mv "$2.part" "$2"; fi
  if [[ "$(shasum -a 256 "$2" | cut -d' ' -f1)" != "$3" ]]; then
    rm -f "$2"; echo "   $2 does not match the official checksum — removed. Please run setup again."; exit 1
  fi
}
get https://github.com/TencentARC/GFPGAN/releases/download/v1.3.4/GFPGANv1.4.pth models/GFPGANv1.4.pth \
    e2cd4703ab14f4d01fd1383a8a8b266f9a5833dacee8e6a79d3bf21a1b6be5ad
get https://github.com/xinntao/facexlib/releases/download/v0.1.0/detection_Resnet50_Final.pth models/gfpgan/weights/detection_Resnet50_Final.pth \
    6d1de9c2944f2ccddca5f5e010ea5ae64a39845a86311af6fdf30841b0a5a16d
get https://github.com/xinntao/facexlib/releases/download/v0.2.2/parsing_parsenet.pth models/gfpgan/weights/parsing_parsenet.pth \
    3d558d8d0e42c20224f13cf5a29c79eba2d59913419f945545d8cf7b72920de2

echo "== exiftool (writes captions into photo metadata)"
if ! command -v exiftool >/dev/null; then
  if command -v brew >/dev/null; then brew install exiftool
  else echo "   Homebrew not found — install exiftool manually (https://exiftool.org) to get captions in metadata."; fi
fi

echo "== Check"
.venv/bin/python scripts/check_setup.py   # (this script runs inside system/)
