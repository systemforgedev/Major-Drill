"""Settings, loaded from a TOML file with sane defaults for every key."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path


@dataclass
class ModelCfg:
    # provider: "anthropic" (cloud, needs a key) | "openai_compat" (any local/OpenAI-style
    # server such as Ollama or LM Studio) | "mock" | "none"
    provider: str = "anthropic"
    model: str = "claude-haiku-5-5"
    base_url: str = ""          # only for openai_compat, e.g. http://127.0.0.1:8000/v1
    api_key_env: str = ""       # env var holding a key for openai_compat servers
    effort: str = "low"         # Claude effort: low | medium | high | xhigh | max
    max_tokens: int = 4000
    timeout_s: float = 60.0     # openai_compat: give up on a request after this long


@dataclass
class IngestCfg:
    frame_every_s: float = 3.0  # sample one frame every N seconds of video
    max_width: int = 1280       # downscale frames to this width before analysis
    jpeg_quality: int = 3       # ffmpeg -q:v (2 best .. 31 worst)
    batch_size: int = 8         # frames per fast-tier request in offline review


@dataclass
class LiveCfg:
    frame_every_s: float = 1.5  # how often the fast tier looks at the screen
    min_gap_s: float = 6.0      # never speak more often than this
    repeat_gap_s: float = 20.0  # don't repeat the same call within this window
    min_confidence: float = 0.6
    max_latency_s: float = 3.0  # drop advice that arrives later than this
    save_frame_every_s: float = 5.0
    record_video: bool = True
    video_fps: int = 30
    monitor: int = 1


@dataclass
class TelemetryCfg:
    # War Thunder's own local map/HUD server. Optional, live mode only.
    enabled: bool = True
    url: str = "http://127.0.0.1:8111"
    poll_hz: float = 2.0


@dataclass
class VoiceCfg:
    enabled: bool = True
    rate: int = 190


@dataclass
class Config:
    game: str = "war_thunder"   # built-in profile name or path to a profile .toml
    player_name: str = ""       # your in-game nickname, helps spot your deaths in the kill feed
    matches_dir: str = "matches"
    # Who decides the calls and who writes the review. The defaults need no API key.
    drill: str = "protocols"    # "protocols" (local rules, free) | "model" (a model picks calls, see [fast])
    major: str = "local"        # "local" (rules-based review, free) | "model" (a model reviews, see [deep])
    protocols: str = ""         # protocol file; default protocols/<game key>.toml
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    # Optional local vision model ("kev") that describes frames for the protocols.
    # provider "none" = rules only. See PROTOCOLS.md for Ollama / LM Studio setup.
    vision: ModelCfg = field(default_factory=lambda: ModelCfg(provider="none", model="", max_tokens=400))
    fast: ModelCfg = field(default_factory=ModelCfg)
    deep: ModelCfg = field(default_factory=lambda: ModelCfg(
        model="claude-opus-5-5", effort="high", max_tokens=32000))
    ingest: IngestCfg = field(default_factory=IngestCfg)
    live: LiveCfg = field(default_factory=LiveCfg)
    telemetry: TelemetryCfg = field(default_factory=TelemetryCfg)
    voice: VoiceCfg = field(default_factory=VoiceCfg)
    # Extra Drill candidates for `wtmate bench`: list of tables with name + ModelCfg keys.
    contenders: list = field(default_factory=list)


def _merge(obj, data: dict):
    for f in fields(obj):
        if f.name not in data:
            continue
        cur = getattr(obj, f.name)
        if is_dataclass(cur):
            _merge(cur, data[f.name])
        else:
            setattr(obj, f.name, type(cur)(data[f.name]) if cur is not None else data[f.name])
    if hasattr(obj, "drill") and obj.drill not in ("protocols", "model"):
        raise ValueError(f"drill must be 'protocols' or 'model', not {obj.drill!r}")
    if hasattr(obj, "major") and obj.major not in ("local", "model"):
        raise ValueError(f"major must be 'local' or 'model', not {obj.major!r}")
    unknown = set(data) - {f.name for f in fields(obj)}
    if unknown:
        raise ValueError(f"Unknown config keys in [{type(obj).__name__}]: {sorted(unknown)}")
    return obj


def load_config(path: str | Path | None = None) -> Config:
    cfg = Config()
    if path is None:
        default = Path("wtmate.toml")
        path = default if default.exists() else None
    if path:
        with open(path, "rb") as fh:
            _merge(cfg, tomllib.load(fh))
    return cfg
