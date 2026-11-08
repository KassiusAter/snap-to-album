# Third-party notices

This project stands on the work of others. This page lists everything it uses, under which
license, and what you should know before using it — in plain words.

The project's own code (scripts, templates, the Claude Code skill) is released under the MIT
License (see `LICENSE`).

## 1. Code included in this repository

### Colorization network architecture (`system/scripts/ai_models.py`, function `_eccv16`)

The layer layout of the colorization network is re-implemented after the reference code of
*Colorful Image Colorization* by Richard Zhang, Phillip Isola and Alexei A. Efros (ECCV 2016),
https://github.com/richzhang/colorization, so that the authors' official weights load unchanged.
That code is licensed under the BSD 2-Clause License:

```
Copyright (c) 2016, Richard Zhang, Phillip Isola, Alexei A. Efros
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

No other third-party code is copied into this repository.

## 2. Software installed by `setup.sh` (not part of this repository)

`system/setup.sh` downloads these packages from their official sources into a local folder (`system/.venv/`).
They keep their own licenses; this project only calls them.

| Component | Used for | License | Source |
|---|---|---|---|
| OpenCV (`opencv-python-headless`) | photo detection, perspective, colors | Apache 2.0 | https://opencv.org |
| NumPy, Pillow | image arrays, image files | BSD / MIT-CMU (HPND) | https://numpy.org, https://python-pillow.org |
| PyTorch, torchvision | running the neural networks | BSD-style | https://pytorch.org |
| GFPGAN | face restoration | Apache 2.0 (see its LICENSE for bundled third-party parts) | https://github.com/TencentARC/GFPGAN |
| BasicSR | GFPGAN's toolbox; also provides the Real-ESRGAN network | Apache 2.0 | https://github.com/XPixelGroup/BasicSR |
| facexlib | face detection for GFPGAN | MIT | https://github.com/xinntao/facexlib |
| ExifTool (via Homebrew) | writing captions into photo metadata, reading capture times | Perl Artistic License / GPL | https://exiftool.org |

**Two small compatibility fixes, made openly.** GFPGAN, BasicSR and facexlib are published as
source packages whose install script no longer works on Python 3.13+, and BasicSR refers to a
torchvision module that was later renamed. `system/setup.sh` downloads the official packages from PyPI
and changes exactly those lines on your computer (both changes are visible in `system/setup.sh`). The
modified files stay in your local `system/.venv/` and are not redistributed.

## 3. Model weights (downloaded on your computer, not part of this repository)

| Weights | Used for | License of the release | Downloaded from |
|---|---|---|---|
| GFPGAN v1.4 | face restoration | Apache 2.0 | GitHub release of TencentARC/GFPGAN |
| RetinaFace ResNet50, ParseNet (facexlib) | finding faces | MIT | GitHub release of xinntao/facexlib |
| Real-ESRGAN `realesr-general-x4v3` (optional) | upscaling | BSD 3-Clause | GitHub release of xinntao/Real-ESRGAN |
| ECCV16 colorization (optional) | colorization | BSD 2-Clause | the authors' official download (richzhang/colorization) |

### A fair note on training data

Neural networks learn from photo collections, and some of those collections have their own terms:
GFPGAN was trained on FFHQ (face photos from Flickr; the dataset is licensed for non-commercial
use), and the colorization model on ImageNet (whose terms allow non-commercial research and
education). Whether such terms also apply to a trained model is not settled.

- **Private, family use** — what this project is made for — is not a concern in practice.
- **Commercial use** (for example a paid digitization service built on this project): please check
  the terms of the models and their training data yourself, or use the `none` / `colors`
  options only, which use no neural network at all.

## 4. Your photos

The photos you process remain yours — and sometimes someone else's. See *Fair use of your albums*
in `README.md`.
