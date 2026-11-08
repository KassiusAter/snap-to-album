"""Optional AI add-ons: upscaling (Real-ESRGAN) and colorization of black-and-white photos.

Both run locally with PyTorch (Apple GPU via MPS, NVIDIA GPU via CUDA, otherwise CPU).
Their weights are downloaded on first use from the official releases into models/:
  - Real-ESRGAN "realesr-general-x4v3" (~5 MB, BSD-3-Clause, github.com/xinntao/Real-ESRGAN)
  - Colorization ECCV16, Zhang, Isola & Efros, "Colorful Image Colorization" (~129 MB,
    BSD-2-Clause, github.com/richzhang/colorization)

The colorization network layout in _eccv16() is adapted from the authors' reference code:
  Copyright (c) 2016, Richard Zhang, Phillip Isola, Alexei A. Efros. All rights reserved.
  BSD 2-Clause License — full text in THIRD_PARTY_NOTICES.md.

Be aware: an upscaler invents fine detail (it can add texture or "cracks" that were never
there), and a colorizer guesses colors — skin, sky and grass are usually plausible, clothes
and objects are a guess. That is why both are opt-in and shown on your test photo first.
"""
import os
import subprocess

import cv2
import numpy as np

import common

# file, official URL, SHA-256 (full, or the prefix the authors publish in the file name)
WEIGHTS = {
    "upscale": ("realesr-general-x4v3.pth",
                "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth",
                "8dc7edb9ac80ccdc30c3a5dca6616509367f05fbc184ad95b731f05bece96292"),
    "colorize": ("colorization_eccv16.pth",
                 "https://colorizers.s3.us-east-2.amazonaws.com/colorization_release_v2-9b330a0b.pth",
                 "9b330a0b"),
}


def sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure(name):
    """Path to the weights, downloading them once if needed."""
    file, url, checksum = WEIGHTS[name]
    path = os.path.join(common.MODELS, file)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        os.makedirs(common.MODELS, exist_ok=True)
        print(f"Downloading {file} (once) from {url.split('/')[2]} …")
        tmp = path + ".part"
        # system curl: uses the macOS certificate store (python.org builds of Python have none)
        subprocess.run(["curl", "-fL", "--progress-bar", "-o", tmp, url], check=True)
        if not sha256(tmp).startswith(checksum):
            os.remove(tmp)
            raise RuntimeError(f"{file}: download does not match the official checksum — not used")
        os.replace(tmp, path)
    return path


class Upscaler:
    """Real-ESRGAN (general x4 v3). Output = factor × input, processed in tiles to save memory."""

    def __init__(self):
        import torch
        from basicsr.archs.srvgg_arch import SRVGGNetCompact
        self.torch = torch
        self.device = common.device()
        self.net = SRVGGNetCompact(num_in_ch=3, num_out_ch=3, num_feat=64, num_conv=32, upscale=4, act_type="prelu")
        self.net.load_state_dict(torch.load(ensure("upscale"), map_location="cpu", weights_only=True)["params"])
        self.net.eval().to(self.device)

    def apply(self, bgr, factor=2, tile=384, pad=16):
        """Each tile is upscaled 4×, brought to the requested factor right away and written into
        a uint8 result of the final size — memory stays small even for large photos."""
        torch = self.torch
        h, w = bgr.shape[:2]
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        out = np.zeros((h * factor, w * factor, 3), np.uint8)
        with torch.no_grad():
            for y in range(0, h, tile):
                for x in range(0, w, tile):
                    y0, x0 = max(y - pad, 0), max(x - pad, 0)
                    y1, x1 = min(y + tile + pad, h), min(x + tile + pad, w)
                    t = torch.from_numpy(rgb[y0:y1, x0:x1].astype(np.float32).transpose(2, 0, 1) / 255)
                    r = self.net(t.unsqueeze(0).to(self.device)).clamp(0, 1).squeeze(0).cpu().numpy()
                    ty, tx = (y - y0) * 4, (x - x0) * 4
                    th, tw = min(y + tile, h) - y, min(x + tile, w) - x
                    part = (r.transpose(1, 2, 0)[ty:ty + th * 4, tx:tx + tw * 4] * 255).round().astype(np.uint8)
                    if factor != 4:
                        part = cv2.resize(part, (tw * factor, th * factor), interpolation=cv2.INTER_AREA)
                    out[y * factor:(y + th) * factor, x * factor:(x + tw) * factor] = part
        return cv2.cvtColor(out, cv2.COLOR_RGB2BGR)


def _eccv16():
    """ECCV16 colorization network (same layer layout as the authors' reference code,
    so the official weights load unchanged)."""
    import torch.nn as nn

    def block(cfg, norm=True):
        layers = []
        for cin, cout, stride, dil in cfg:
            layers += [nn.Conv2d(cin, cout, 3, stride=stride, padding=dil, dilation=dil, bias=True), nn.ReLU(True)]
        if norm:
            layers.append(nn.BatchNorm2d(cfg[-1][1]))
        return nn.Sequential(*layers)

    class ECCV16(nn.Module):
        def __init__(self):
            super().__init__()
            self.model1 = block([(1, 64, 1, 1), (64, 64, 2, 1)])
            self.model2 = block([(64, 128, 1, 1), (128, 128, 2, 1)])
            self.model3 = block([(128, 256, 1, 1), (256, 256, 1, 1), (256, 256, 2, 1)])
            self.model4 = block([(256, 512, 1, 1), (512, 512, 1, 1), (512, 512, 1, 1)])
            self.model5 = block([(512, 512, 1, 2)] * 3)
            self.model6 = block([(512, 512, 1, 2)] * 3)
            self.model7 = block([(512, 512, 1, 1)] * 3)
            self.model8 = nn.Sequential(nn.ConvTranspose2d(512, 256, 4, stride=2, padding=1, bias=True), nn.ReLU(True),
                                        nn.Conv2d(256, 256, 3, padding=1, bias=True), nn.ReLU(True),
                                        nn.Conv2d(256, 256, 3, padding=1, bias=True), nn.ReLU(True),
                                        nn.Conv2d(256, 313, 1, bias=True))
            self.softmax = nn.Softmax(dim=1)
            self.model_out = nn.Conv2d(313, 2, 1, bias=False)
            self.upsample4 = nn.Upsample(scale_factor=4, mode="bilinear")

        def forward(self, l):
            x = self.model1((l - 50) / 100)
            for m in (self.model2, self.model3, self.model4, self.model5, self.model6, self.model7, self.model8):
                x = m(x)
            return self.upsample4(self.model_out(self.softmax(x))) * 110

    return ECCV16()


class Colorizer:
    """Predicts colors at 256 px and puts them under the full-resolution brightness channel."""

    def __init__(self):
        import torch
        self.torch = torch
        self.device = common.device()
        self.net = _eccv16()
        self.net.load_state_dict(torch.load(ensure("colorize"), map_location="cpu", weights_only=True))
        self.net.eval().to(self.device)

    def apply(self, bgr, saturation=1.0):
        torch = self.torch
        h, w = bgr.shape[:2]
        lab = cv2.cvtColor(bgr.astype(np.float32) / 255, cv2.COLOR_BGR2LAB)  # L 0–100
        small = cv2.resize(lab[:, :, 0], (256, 256), interpolation=cv2.INTER_AREA)
        with torch.no_grad():
            ab = self.net(torch.from_numpy(small)[None, None].to(self.device)).cpu().numpy()[0].transpose(1, 2, 0)
        ab = cv2.resize(ab, (w, h), interpolation=cv2.INTER_LINEAR) * saturation
        out = cv2.cvtColor(np.dstack([lab[:, :, 0], ab]).astype(np.float32), cv2.COLOR_LAB2BGR)
        return np.clip(out * 255, 0, 255).astype(np.uint8)
