"""Cheap HUD readers: turn one screenshot into plain facts without any AI model.

Each detector looks at one box of the screen (given as fractions of the width
and height, so it works at any resolution) and writes one or more facts, for
example `hp = 360`, `extraction_available = true` or `enemies_right = 2`.
Protocols (see protocols.py) then pick a call from those facts.

Detector types:
  colour_share  share of pixels in the box that match a colour (0..1)
  bar           how full a left-to-right bar is (0..1)
  blips         coloured marks on a minimap, counted per side of the player
  change        how much the box changed since the last frame (0..1)
  ocr_number    a number read with Tesseract OCR (optional install)
  ocr_text      text read with Tesseract OCR (optional install)

Detectors are defined in the game's protocol file under [[detector]].
"""
from __future__ import annotations

import io
import re
import shutil
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

TYPES = ("colour_share", "bar", "blips", "change", "ocr_number", "ocr_text")


@dataclass
class Detector:
    name: str                       # fact name it writes (blips writes name_left, name_right, ...)
    type: str
    box: list[float]                # [x0, y0, x1, y1] as fractions of the screen
    colour: list[int] = field(default_factory=lambda: [255, 255, 255])
    tolerance: int = 60             # max distance per channel from `colour`
    threshold: float | None = None  # if set, also writes a yes/no fact: value >= threshold
    flag: str = ""                  # name of that yes/no fact (default: <name>_on)
    min_size: int = 1               # blips: smallest blob in pixels (at 1280 wide)
    scale: int = 3                  # OCR: upscale the crop this much first
    note: str = ""

    def check(self):
        if self.type not in TYPES:
            raise ValueError(f"detector {self.name!r}: unknown type {self.type!r}; use one of {TYPES}")
        if len(self.box) != 4 or not all(0 <= v <= 1 for v in self.box) or \
                self.box[0] >= self.box[2] or self.box[1] >= self.box[3]:
            raise ValueError(f"detector {self.name!r}: box must be [x0, y0, x1, y1] fractions, x0<x1, y0<y1")
        return self


def to_array(frame) -> np.ndarray:
    """JPEG/PNG bytes, a PIL image or an array -> HxWx3 uint8 array."""
    if isinstance(frame, np.ndarray):
        return frame
    if isinstance(frame, (bytes, bytearray)):
        frame = Image.open(io.BytesIO(frame))
    return np.asarray(frame.convert("RGB"))


def crop(img: np.ndarray, box) -> np.ndarray:
    h, w = img.shape[:2]
    x0, y0, x1, y1 = box
    return img[int(y0 * h):max(int(y0 * h) + 1, int(y1 * h)), int(x0 * w):max(int(x0 * w) + 1, int(x1 * w))]


def colour_mask(region: np.ndarray, colour, tolerance: int) -> np.ndarray:
    diff = np.abs(region.astype(np.int16) - np.array(colour, dtype=np.int16))
    return (diff <= tolerance).all(axis=2)


def _blobs(mask: np.ndarray, min_size: int) -> list[tuple[float, float, int]]:
    """Connected blobs in a small mask -> [(cx, cy, size)]. Pure numpy/python, minimaps are tiny."""
    seen = np.zeros_like(mask, dtype=bool)
    out = []
    h, w = mask.shape
    for y, x in zip(*np.nonzero(mask)):
        if seen[y, x]:
            continue
        stack, pts = [(y, x)], []
        seen[y, x] = True
        while stack:
            cy, cx = stack.pop()
            pts.append((cy, cx))
            for ny in range(cy - 1, cy + 2):  # 8-connected, so thin marks hold together
                for nx in range(cx - 1, cx + 2):
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
        if len(pts) >= min_size:
            ys, xs = zip(*pts)
            out.append((sum(xs) / len(xs), sum(ys) / len(ys), len(pts)))
    return out


def ocr_available() -> bool:
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return bool(shutil.which("tesseract")) or _windows_tesseract() is not None


def _windows_tesseract():
    import os

    p = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    return p if os.path.exists(p) else None


def _ocr(region: np.ndarray, scale: int, digits: bool) -> str:
    import pytesseract

    exe = _windows_tesseract()
    if exe and not shutil.which("tesseract"):
        pytesseract.pytesseract.tesseract_cmd = exe
    img = Image.fromarray(region).convert("L")
    img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    cfg = "--psm 6" + (" -c tessedit_char_whitelist=0123456789." if digits else "")
    return pytesseract.image_to_string(img, config=cfg).strip()


class HudReader:
    """Runs every detector over a frame. Keeps the last frame for `change`."""

    def __init__(self, detectors: list[Detector]):
        self.detectors = [d.check() for d in detectors]
        self._prev: dict[str, np.ndarray] = {}
        self.ocr = ocr_available()
        self.skipped = sorted({d.name for d in self.detectors if d.type.startswith("ocr") and not self.ocr})

    def read(self, frame) -> dict:
        img = to_array(frame)
        scale = img.shape[1] / 1280  # min_size is given at 1280 wide
        facts: dict = {}
        for d in self.detectors:
            region = crop(img, d.box)
            if d.type == "colour_share":
                v = float(colour_mask(region, d.colour, d.tolerance).mean())
                facts[d.name] = round(v, 4)
            elif d.type == "bar":
                cols = colour_mask(region, d.colour, d.tolerance).mean(axis=0) > 0.5
                v = float(cols.mean())  # share of the bar's columns that are filled
                facts[d.name] = round(v, 3)
            elif d.type == "blips":
                mask = colour_mask(region, d.colour, d.tolerance)
                blobs = _blobs(mask, max(1, round(d.min_size * scale * scale)))
                h, w = mask.shape
                cx, cy = w / 2, h / 2  # the player sits in the middle of the minimap
                sides = {"left": 0, "right": 0, "front": 0, "behind": 0}
                for bx, by, _ in blobs:
                    dx, dy = bx - cx, by - cy
                    if abs(dx) >= abs(dy):
                        sides["right" if dx > 0 else "left"] += 1
                    else:
                        sides["behind" if dy > 0 else "front"] += 1
                for k, n in sides.items():
                    facts[f"{d.name}_{k}"] = n
                facts[f"{d.name}_total"] = len(blobs)
                v = len(blobs)
            elif d.type == "change":
                small = np.asarray(Image.fromarray(region).convert("L").resize((64, 36)), dtype=np.int16)
                prev = self._prev.get(d.name)
                v = float(np.abs(small - prev).mean() / 255) if prev is not None else 0.0
                self._prev[d.name] = small
                facts[d.name] = round(v, 4)
            elif d.type in ("ocr_number", "ocr_text"):
                if not self.ocr:
                    continue  # missing facts just make conditions false
                text = _ocr(region, d.scale, d.type == "ocr_number")
                if d.type == "ocr_number":
                    m = re.search(r"\d+(?:\.\d+)?", text)
                    if not m:
                        continue
                    v = float(m.group())
                    facts[d.name] = v
                else:
                    v = text.lower()
                    facts[d.name] = v
            if d.threshold is not None and d.type not in ("ocr_text",):
                facts[d.flag or f"{d.name}_on"] = bool(v >= d.threshold)
        return facts
