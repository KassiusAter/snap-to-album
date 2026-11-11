"""Enhances the cropped photos with the tool chosen in the first-run step (config.json).

  system/.venv/bin/python system/scripts/enhance.py <album> [IMG_0001_1 …]

  none            crops/ → enhanced/ unchanged
  colors          crops/ → enhanced/ with automatic color/contrast restoration
  colors+facesNN  as above, then GFPGAN face restoration mixed NN % with the original
                  (so faces keep their real features)
Optional AI add-ons (settings "colorize" and "upscale", see ai_models.py):
  colorize bw     black-and-white photos get AI colors (before face restoration)
  upscale 2x/4x   Real-ESRGAN upscaling as the last step
Everything after the base step is written to final/ (the album uses final/ when it exists).

Color restoration (OpenCV, CPU):
  - black-and-white photos: tinted/yellowed paper back to neutral gray, tones stretched,
    gentle local contrast (CLAHE)
  - color photos: faded prints from the 70s–90s drift to pink/orange (the cyan dye fades
    fastest) — per-channel levels, then a per-channel gamma pulling each channel's median
    towards the overall median (strength depends on how strong the cast is)
  - clippings (album.json "clippings") and back sides (backs.json): only a gentle stretch,
    paper keeps its tone; no AI add-ons
Face restoration (GFPGAN v1.4, PyTorch) runs on the local GPU when available
(Apple Silicon: MPS, NVIDIA: CUDA), otherwise on the CPU.
"""
import glob
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def trim_border(img, share=0.012):
    """Cuts off leftovers of the white print border / background at the crop edges."""
    h, w = img.shape[:2]
    d = int(share * min(h, w))
    return img[d:h - d, d:w - d]


def _stretch(f, lo_p=0.5, hi_p=99.5):
    out = np.empty_like(f)
    for k in range(3):
        lo, hi = np.percentile(f[:, :, k], (lo_p, hi_p))
        out[:, :, k] = (f[:, :, k] - lo) * 255 / max(hi - lo, 1)
    return np.clip(out, 0, 255)


def is_black_and_white(img):
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    return lab[:, :, 1].std() < 4 and lab[:, :, 2].std() < 6


def black_and_white(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    lo, hi = np.percentile(g, (0.5, 99.5))
    g = np.clip((g.astype(np.float32) - lo) * 255 / max(hi - lo, 1), 0, 255).astype(np.uint8)
    g = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8)).apply(g)
    return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)


def color(img):
    f = _stretch(img.astype(np.float32), 0.3, 99.7) / 255
    med = np.array([np.median(f[:, :, k]) for k in range(3)])
    target = med.mean()
    cast = float(np.abs(med - target).max() * 255)
    strength = float(np.clip(cast / 40, 0.35, 0.8))  # keeps a little of the warm tone
    for k in range(3):
        g = np.log(np.clip(target, 0.05, 0.95)) / np.log(np.clip(med[k], 0.05, 0.95))
        f[:, :, k] = np.power(f[:, :, k], 1 + strength * (g - 1))
    bgr = np.clip(f * 255, 0, 255).astype(np.uint8)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = cv2.createCLAHE(clipLimit=1.2, tileGridSize=(8, 8)).apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def clipping(img):
    f = img.astype(np.float32)
    return (0.6 * _stretch(f, 1, 99.8) + 0.4 * f).astype(np.uint8)


def restore_colors(img, is_clipping=False):
    img = trim_border(img)
    if is_clipping:
        return clipping(img), "clipping"
    if is_black_and_white(img):
        return black_and_white(img), "b&w"
    return color(img), "color"


class Faces:
    """GFPGAN face restoration, blended with the original: 0 = original, 1 = full GFPGAN."""

    def __init__(self):
        from gfpgan import GFPGANer
        self.device = common.device()
        cwd = os.getcwd()
        os.chdir(common.MODELS)  # facexlib looks for its weights in ./gfpgan/weights
        try:
            self.restorer = GFPGANer(model_path=os.path.join(common.MODELS, "GFPGANv1.4.pth"), upscale=1,
                                     arch="clean", channel_multiplier=2, bg_upsampler=None, device=self.device)
        finally:
            os.chdir(cwd)

    # Above this size faces are restored on a smaller copy: on a full-resolution phone shot of a
    # class photo (30 faces, 4000 px) GFPGAN took about a minute per photo, at 2400 px a few seconds.
    # Only the change GFPGAN makes is scaled back up and added to the full-size photo, so everything
    # that is not a face keeps its full resolution.
    MAX_SIDE = 2400

    def apply(self, img, strength):
        h, w = img.shape[:2]
        k = min(1.0, self.MAX_SIDE / max(h, w))
        work = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else img
        cwd = os.getcwd()
        os.chdir(common.MODELS)
        try:
            _, faces, out = self.restorer.enhance(work, has_aligned=False, only_center_face=False, paste_back=True)
        finally:
            os.chdir(cwd)
        if not faces:
            return img, 0
        if k == 1:
            return cv2.addWeighted(out, strength, img, 1 - strength, 0), len(faces)
        change = cv2.resize(out.astype(np.float32) - work.astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
        return np.clip(img.astype(np.float32) + strength * change, 0, 255).astype(np.uint8), len(faces)


def face_strength(option):
    return int(option.split("faces")[1]) / 100 if "faces" in option else 0


def upscale_factor(cfg):
    return {"2x": 2, "4x": 4}.get(cfg.get("upscale"), 1)


class Pipeline:
    """All steps chosen in config.json, in this order:
    colors → colorization (black-and-white only) → faces → upscaling.
    Neural networks are loaded only when the first photo actually needs them."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.base = cfg["enhancement"]
        self._models = None

    def extras(self):
        return bool(face_strength(self.base) or self.cfg.get("colorize") == "bw" or upscale_factor(self.cfg) > 1)

    def models(self):
        if self._models is None:
            faces = Faces() if face_strength(self.base) else None
            colorizer = upscaler = None
            if self.cfg.get("colorize") == "bw" or upscale_factor(self.cfg) > 1:
                import ai_models
                colorizer = ai_models.Colorizer() if self.cfg.get("colorize") == "bw" else None
                upscaler = ai_models.Upscaler() if upscale_factor(self.cfg) > 1 else None
            self._models = (faces, colorizer, upscaler)
            print(f"AI steps run on: {common.device()}")
        return self._models

    def run(self, crop, gentle=False):
        """Returns (after base step, after all steps or None, description).
        gentle = clipping or back side: base step only, never AI steps."""
        if self.base == "none":
            base, kind = crop, "unchanged"
        else:
            base, kind = restore_colors(crop, gentle)
        if gentle or not self.extras():
            return base, None, kind
        faces, colorizer, upscaler = self.models()
        img, notes = base, [kind]
        if colorizer and is_black_and_white(crop):
            img = colorizer.apply(img)
            notes.append("colorized")
        if faces:
            img, n = faces.apply(img, face_strength(self.base))
            notes.append(f"faces: {n}")
        if upscaler:
            img = upscaler.apply(img, upscale_factor(self.cfg))
            notes.append(f"upscaled {self.cfg['upscale']}")
        return base, img, ", ".join(notes)


def process_photo(album_d, j, pipe, gentle):
    """Processes one photo (wherever it lives — it may belong to another album folder) and
    writes enhanced/ and final/. The one place that does this, for enhance.py and the build."""
    x = common.photo_dir(album_d, j)
    if not x:
        return f"not found in any album — skipped"
    crop = cv2.imread(os.path.join(x, "crops", f"{j}.jpg"))
    base, final, note = pipe.run(crop, gentle)
    for sub in ("enhanced", "final"):
        os.makedirs(os.path.join(x, sub), exist_ok=True)
    cv2.imwrite(os.path.join(x, "enhanced", f"{j}.jpg"), base, [cv2.IMWRITE_JPEG_QUALITY, 93])
    final_path = os.path.join(x, "final", f"{j}.jpg")
    if final is not None:
        cv2.imwrite(final_path, final, [cv2.IMWRITE_JPEG_QUALITY, 95])
    elif os.path.exists(final_path):
        os.remove(final_path)  # left over from an earlier run with more steps
    with open(os.path.join(x, "enhanced", f"{j}.cfg"), "w") as f:   # what it was made with
        f.write(common.enhancement_signature(pipe.cfg, gentle))
    return note


def gentle_ids(album, d):
    """Clippings and back sides (paper with writing): base step only, no AI steps."""
    return common.clippings(album, d) | set(common.backs(d))


if __name__ == "__main__":
    cfg = common.require_config()
    name = sys.argv[1]
    d = common.album_dir(name)
    album = common.load_album(name) if os.path.exists(os.path.join(d, "album.json")) else {"clippings": []}
    gentle = gentle_ids(album, d)
    ids = sys.argv[2:] or [os.path.splitext(os.path.basename(p))[0] for p in sorted(glob.glob(os.path.join(d, "crops", "*.jpg")))]
    pipe = Pipeline(cfg)
    print(f"Steps: {cfg['enhancement']}, colorize {cfg['colorize']}, upscale {cfg['upscale']}")
    for j in ids:
        print(f"{j}: {process_photo(d, j, pipe, j in gentle)}")
