"""Benchmark: run several Drill candidates on the same footage and score them.

Scores answer the questions that matter for a live teammate:
  call_accuracy  how often its call matched what Major said was right (or should have been said)
  death_recall   how many of the reference deaths it noticed
  grid_match     how often its minimap reading matched the reference reading
  calls_per_min  how talkative it is (the "yapping" score; lower is usually better)
  p50/p90 lag    how long one frame takes (what live mode would feel like)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .config import Config, ModelCfg
from .drill import latency_stats, observe
from .match import Match
from .memory import Memory
from .models import make_provider
from .schema import CALLS

WINDOW_S = 6.0  # a call within this many seconds of Major's moment counts


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "model"


def contender_cfgs(cfg: Config) -> list[tuple[str, ModelCfg]]:
    out = [("drill (" + cfg.fast.model + ")", cfg.fast)]
    for c in cfg.contenders:
        c = dict(c)
        name = c.pop("name", c.get("model", "model"))
        out.append((name, ModelCfg(**c)))
    return out


def expected_calls(debrief: dict) -> list[tuple[float, str]]:
    """Major's verdicts become the answer key."""
    out = []
    for g in debrief.get("call_grades", []):
        if g["grade"] == "right" and g["call"] in CALLS:
            out.append((g["t"], g["call"]))
        elif g.get("should_have_said") in CALLS and g["should_have_said"] != "none":
            out.append((g["t"], g["should_have_said"]))
    return out


def score(candidate: list[dict], reference: list[dict], debrief: dict, duration_s: float,
          min_conf: float = 0.6) -> dict:
    spoken = [o for o in candidate if o.get("call", "none") != "none" and o.get("confidence", 0) >= min_conf]
    key = expected_calls(debrief)
    hits = sum(1 for t, c in key if any(o["call"] == c and abs(o["t"] - t) <= WINDOW_S for o in spoken))
    ref_deaths = [o["t"] for o in reference if o.get("event") == "death"]
    caught = sum(1 for t in ref_deaths if any(o.get("event") == "death" and abs(o["t"] - t) <= WINDOW_S
                                               for o in candidate))
    by_t = {o["t"]: o for o in candidate}
    pairs = [(r, by_t.get(r["t"])) for r in reference if r.get("minimap_grid")]
    grid_ok = sum(1 for r, c in pairs if c and c.get("minimap_grid", "").upper() == r["minimap_grid"].upper())
    return {
        "call_accuracy": round(hits / len(key), 3) if key else None,
        "answer_key_size": len(key),
        "death_recall": round(caught / len(ref_deaths), 3) if ref_deaths else None,
        "grid_match": round(grid_ok / len(pairs), 3) if pairs else None,
        "calls_per_min": round(len(spoken) / max(duration_s / 60, 1e-6), 2),
    }


def run_bench(cfg: Config, match: Match, batch_size: int = 1, limit: int | None = None,
              only: list[str] | None = None, progress=print) -> dict:
    """batch_size=1 measures live-like latency; larger batches are cheaper."""
    reference = match.read("observations")
    debrief = match.read_json("debrief.json", {}) or {}
    if not reference:
        raise RuntimeError("Run `wtmate review` on this match first: the bench needs a reference read.")
    frames = match.frames()[:limit] if limit else match.frames()
    duration = (frames[-1][0] - frames[0][0] + cfg.ingest.frame_every_s) if frames else 1
    reference = [r for r in reference if r["t"] <= frames[-1][0] + 0.01] if frames else []
    memory = Memory(cfg.matches_dir)
    out_dir = match.root / "bench"
    out_dir.mkdir(exist_ok=True)
    results = {}
    for name, mcfg in contender_cfgs(cfg):
        if only and not any(o.lower() in name.lower() for o in only):
            continue
        progress(f"[bench] {name}: {len(frames)} frames")
        provider = make_provider(mcfg)
        obs_all, lat = [], []
        try:
            for i in range(0, len(frames), batch_size):
                chunk = [(t, Path(p).read_bytes()) for t, p in frames[i:i + batch_size]]
                obs, res = observe(provider, memory, chunk)
                obs_all += obs
                lat.append(res.latency_s / len(chunk))
        except Exception as e:
            progress(f"[bench] {name} failed: {e}")
            results[name] = {"error": str(e)}
            continue
        s = score(obs_all, reference, debrief, duration) | latency_stats(lat) | {"model": mcfg.model,
                                                                               "provider": mcfg.provider}
        results[name] = s
        (out_dir / f"{_slug(name)}.jsonl").write_text("\n".join(json.dumps(o) for o in obs_all), encoding="utf-8")
    (out_dir / "scores.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    build_compare(match)
    return results


def build_compare(match: Match) -> Path:
    """Side-by-side page: what each model would have said at each moment."""
    from .review import _render

    out_dir = match.root / "bench"
    scores = json.loads((out_dir / "scores.json").read_text(encoding="utf-8"))
    runs = {}
    for name in scores:
        p = out_dir / f"{_slug(name)}.jsonl"
        if p.exists():
            runs[name] = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    frames = [{"t": t, "src": f"../frames/{p.name}"} for t, p in match.frames()]
    debrief = match.read_json("debrief.json", {}) or {}
    out = out_dir / "compare.html"
    out.write_text(_render("compare.html", SCORES=scores, RUNS=runs, FRAMES=frames,
                           KEY=[{"t": t, "call": c} for t, c in expected_calls(debrief)]), encoding="utf-8")
    return out
