"""Turn a match folder into numbers for the review page."""
from __future__ import annotations

import re
from collections import Counter

from .match import Match

GRID_RE = re.compile(r"^\s*([A-Za-z])\s*-?\s*(\d{1,2})\s*$")


def parse_grid(s: str):
    m = GRID_RE.match(s or "")
    if not m:
        return None
    # War Thunder minimaps label rows with letters (A at the top) and columns with numbers.
    return int(m.group(2)) - 1, ord(m.group(1).upper()) - ord("A")  # (col, row)


def dedupe_times(times: list[float], gap: float) -> list[float]:
    out = []
    for t in sorted(times):
        if not out or t - out[-1] >= gap:
            out.append(t)
    return out


def match_stats(match: Match, min_conf: float = 0.6) -> dict:
    meta = match.meta()
    obs = match.read("observations")
    events = match.read("events")
    track = match.read("track")
    spoken = match.read("calls")
    debrief = match.read_json("debrief.json", {}) or {}

    deaths = [o["t"] for o in obs if o.get("event") == "death"]
    deaths += [e["t"] for e in events if e.get("type") == "death"]
    kills = [o["t"] for o in obs if o.get("event") == "kill"]
    kills += [e["t"] for e in events if e.get("type") == "kill"]
    deaths, kills = dedupe_times(deaths, 20), dedupe_times(kills, 5)

    calls = spoken or [o for o in obs if o.get("call", "none") != "none" and o.get("confidence", 0) >= min_conf]
    situations = Counter(o.get("situation", "unclear") for o in obs)
    total = sum(situations.values()) or 1

    grid = Counter()
    for o in obs:
        g = parse_grid(o.get("minimap_grid", ""))
        if g and o.get("alive", True):
            grid[g] += 1

    duration = meta.get("duration_s") or max([o["t"] for o in obs] + [p["t"] for p in track] + [0])
    return {
        "id": match.id,
        "duration_s": round(duration, 1),
        "deaths": deaths,
        "kills": kills,
        "calls": [{"t": c["t"], "call": c["call"], "reason": c.get("reason", "")} for c in calls],
        "situations": {k: round(v / total, 3) for k, v in situations.most_common()},
        "grid": [{"col": c, "row": r, "n": n} for (c, r), n in grid.items()],
        "track": [{"t": p["t"], "x": p["x"], "y": p["y"]} for p in track],
        "observations": [{"t": o["t"], "situation": o.get("situation", ""), "event": o.get("event", ""),
                          "grid": o.get("minimap_grid", ""), "threat": o.get("threat", ""),
                          "call": o.get("call", ""), "confidence": o.get("confidence", 0)} for o in obs],
        "mistakes": debrief.get("mistakes", []),
        "top3": debrief.get("top3", []),
        "good_plays": debrief.get("good_plays", []),
        "summary": debrief.get("summary", ""),
        "call_grades": debrief.get("call_grades", []),
        "fast_stats": meta.get("fast_stats", {}),
        "source": meta.get("source", ""),
        "created": meta.get("created"),
    }
