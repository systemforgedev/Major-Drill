"""One folder per match. Everything is plain files so it is easy to inspect.

matches/<id>/
  meta.json          source, duration, timestamps
  video.mp4          the recording (copied or recorded)
  frames/            sampled JPEG frames, named by second: t000123.0.jpg
  observations.jsonl fast-tier reads, one per frame
  track.jsonl        precise positions from game telemetry (live mode only)
  events.jsonl       kill feed / deaths from telemetry (live mode only)
  calls.jsonl        calls actually spoken (live mode only)
  debrief.json       deep-tier review
  review.html        the timeline + heatmap page
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path


class Match:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.frames_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def create(cls, matches_dir: str | Path, label: str = "") -> "Match":
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        name = f"{stamp}-{label}" if label else stamp
        root = Path(matches_dir) / name
        n = 1
        while root.exists():
            n += 1
            root = Path(matches_dir) / f"{name}-{n}"
        m = cls(root)
        m.write_meta({"created": time.time(), "id": root.name})
        return m

    @property
    def id(self) -> str:
        return self.root.name

    @property
    def frames_dir(self) -> Path:
        return self.root / "frames"

    @property
    def video(self) -> Path:
        return self.root / "video.mp4"

    # meta -------------------------------------------------------------
    def meta(self) -> dict:
        p = self.root / "meta.json"
        return json.loads(p.read_text()) if p.exists() else {}

    def write_meta(self, updates: dict):
        meta = self.meta()
        meta.update(updates)
        (self.root / "meta.json").write_text(json.dumps(meta, indent=2))

    # jsonl streams ------------------------------------------------------
    def append(self, stream: str, record: dict):
        with open(self.root / f"{stream}.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    def read(self, stream: str) -> list[dict]:
        p = self.root / f"{stream}.jsonl"
        if not p.exists():
            return []
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]

    def write_json(self, name: str, data):
        (self.root / name).write_text(json.dumps(data, indent=2), encoding="utf-8")

    def read_json(self, name: str, default=None):
        p = self.root / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

    # frames -------------------------------------------------------------
    def frame_path(self, t: float) -> Path:
        return self.frames_dir / f"t{t:08.1f}.jpg"

    def frames(self) -> list[tuple[float, Path]]:
        out = []
        for p in sorted(self.frames_dir.glob("t*.jpg")):
            try:
                out.append((float(p.stem[1:]), p))
            except ValueError:
                continue
        return sorted(out)
