"""Turn an uploaded recording into a match folder with sampled frames.

This is the core, offline path: no game feed, just a video you recorded
(ShadowPlay, OBS, Xbox Game Bar, the game's own replay export, anything).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .config import Config
from .match import Match


def probe_duration(cfg: Config, video: Path) -> float:
    out = subprocess.run(
        [cfg.ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)],
        capture_output=True, text=True, check=True)
    return float(json.loads(out.stdout)["format"]["duration"])


def extract_frames(cfg: Config, video: Path, out_dir: Path, every_s: float,
                   start_s: float = 0.0, end_s: float | None = None) -> list[tuple[float, Path]]:
    """Grab one frame every `every_s` seconds, downscaled, named by timestamp."""
    tmp = out_dir / "_extract"
    tmp.mkdir(parents=True, exist_ok=True)
    cmd = [cfg.ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    if start_s:
        cmd += ["-ss", f"{start_s}"]
    cmd += ["-i", str(video)]
    if end_s is not None:
        cmd += ["-t", f"{end_s - start_s}"]
    cmd += ["-vf", f"fps=1/{every_s},scale='min({cfg.ingest.max_width},iw)':-2",
            "-q:v", str(cfg.ingest.jpeg_quality), str(tmp / "f%06d.jpg")]
    subprocess.run(cmd, check=True)
    frames = []
    for i, p in enumerate(sorted(tmp.glob("f*.jpg"))):
        # fps filter emits the frame at the middle of each interval
        t = round(start_s + i * every_s + every_s / 2, 1)
        dest = out_dir / f"t{t:08.1f}.jpg"
        p.replace(dest)
        frames.append((t, dest))
    shutil.rmtree(tmp, ignore_errors=True)
    return frames


def ingest_video(cfg: Config, video: str | Path, label: str = "", copy: bool = True) -> Match:
    video = Path(video)
    if not video.exists():
        raise FileNotFoundError(video)
    match = Match.create(cfg.matches_dir, label or video.stem[:40])
    if copy:
        if video.suffix.lower() == ".mp4":
            shutil.copy2(video, match.video)
        else:
            # Re-wrap to mp4 so the review page can play it in any browser.
            subprocess.run([cfg.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac",
                            str(match.video)], check=True)
        src = match.video
    else:
        src = video
    duration = probe_duration(cfg, src)
    frames = extract_frames(cfg, src, match.frames_dir, cfg.ingest.frame_every_s)
    match.write_meta({"source": "upload", "source_file": video.name, "duration_s": duration,
                      "frame_every_s": cfg.ingest.frame_every_s, "frames": len(frames),
                      "has_video": copy})
    return match
