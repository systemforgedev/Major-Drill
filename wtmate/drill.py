"""Drill: the fast tier. Reads frames quickly and picks a short call.

Offline it runs over every sampled frame of a recording (batched, so it is
cheap). Live it looks at one frame at a time. The same prompt and schema are
used in both, so offline runs double as a benchmark of the live behaviour.
"""
from __future__ import annotations

import statistics
from pathlib import Path

from .match import Match
from .memory import Memory
from .models import Image, Provider, Text
from .profiles import GameProfile
from .schema import observation_schema

SYSTEM = """You are Drill, a calm, experienced {teammate} in {game}, watching the player's screen.
For each frame, read the situation the way a good teammate would and decide whether to say
one short call. You only see what the player sees. Never guess at hidden enemy positions
beyond what the minimap, kill feed and screen show.

How to read a frame:
{screen_guide}

Choosing a call:
- Prefer "none". Speak only when it would change what the player does in the next 10 seconds.
- Allowed calls: {calls}.
- Give up to 3 hypotheses about what is about to happen, with likelihoods that sum to at most 1.
- confidence is how sure you are the call helps (0 to 1).
- The frame label gives t in seconds. Copy it exactly into "t".

{memory}
"""


def system_prompt(memory: Memory, profile: GameProfile) -> str:
    return SYSTEM.format(teammate=profile.teammate, game=profile.title, screen_guide=profile.screen_guide,
                         calls=", ".join(f'"{c}"' for c in profile.calls), memory=memory.prompt_block())


def _parts_for(frames: list[tuple[float, bytes]]) -> list:
    parts = []
    for t, jpeg in frames:
        parts.append(Text(f"frame t={t:.1f}s"))
        parts.append(Image(jpeg))
    parts.append(Text(f"Return one observation per frame, {len(frames)} in total, in order."))
    return parts


def observe(provider: Provider, memory: Memory, frames: list[tuple[float, bytes]], profile: GameProfile):
    """One request for one or more frames. Returns (observations, Result)."""
    res = provider.complete_json(system_prompt(memory, profile), _parts_for(frames), observation_schema(profile))
    obs = res.data.get("observations", [])
    # Re-anchor timestamps to the frames we sent, in case the model drifted.
    for o, (t, _) in zip(obs, frames):
        o["t"] = t
    return obs, res


def observe_match(match: Match, provider: Provider, memory: Memory, profile: GameProfile,
                  batch_size: int = 8, progress=None) -> dict:
    """Run the fast tier over every frame of a match. Writes observations.jsonl."""
    out = match.root / "observations.jsonl"
    if out.exists():
        out.unlink()
    frames = match.frames()
    latencies, per_frame = [], []
    for i in range(0, len(frames), batch_size):
        chunk = [(t, Path(p).read_bytes()) for t, p in frames[i:i + batch_size]]
        obs, res = observe(provider, memory, chunk, profile)
        latencies.append(res.latency_s)
        per_frame.append(res.latency_s / max(1, len(chunk)))
        for o in obs:
            match.append("observations", o)
        if progress:
            progress(min(i + batch_size, len(frames)), len(frames))
    stats = latency_stats(latencies) | {"frames": len(frames), "batch_size": batch_size,
                                        "per_frame_s": round(statistics.mean(per_frame), 3) if per_frame else None}
    match.write_meta({"fast_stats": stats})
    return stats


def latency_stats(latencies: list[float]) -> dict:
    if not latencies:
        return {"requests": 0}
    s = sorted(latencies)
    return {"requests": len(s), "p50_s": round(statistics.median(s), 3),
            "p90_s": round(s[min(len(s) - 1, int(0.9 * len(s)))], 3), "max_s": round(s[-1], 3)}
