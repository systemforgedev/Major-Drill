"""Build the review pages: one per match (timeline + heatmap + debrief) and a
career page across all matches. Plain HTML files, no server or internet needed."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .match import Match
from .memory import Memory
from .stats import match_stats

ASSETS = Path(__file__).parent / "assets"


def _render(template: str, **values) -> str:
    html = (ASSETS / template).read_text(encoding="utf-8")
    for k, v in values.items():
        # </ inside JSON would close the script tag early
        html = html.replace(f"__{k}__", json.dumps(v).replace("</", "<\\/"))
    return html


def build_review(match: Match, min_conf: float = 0.6) -> Path:
    stats = match_stats(match, min_conf)
    frames = [{"t": t, "src": f"frames/{p.name}"} for t, p in match.frames()]
    media = {"video": "video.mp4" if match.video.exists() else None,
             "map": "map.png" if (match.root / "map.png").exists() else None}
    out = match.root / "review.html"
    out.write_text(_render("review.html", DATA=stats, FRAMES=frames, MEDIA=media), encoding="utf-8")
    return out


def all_matches(matches_dir: str | Path) -> list[Match]:
    root = Path(matches_dir)
    if not root.exists():
        return []
    return [Match(p) for p in sorted(root.iterdir()) if p.is_dir() and (p / "meta.json").exists()]


def build_index(matches_dir: str | Path) -> Path:
    rows, grid = [], Counter()
    for m in all_matches(matches_dir):
        s = match_stats(m)
        for g in s["grid"]:
            grid[(g["col"], g["row"])] += g["n"]
        rows.append({"id": m.id, "href": f"{m.id}/review.html", "duration_s": s["duration_s"],
                     "deaths": len(s["deaths"]), "kills": len(s["kills"]), "calls": len(s["calls"]),
                     "mistakes": [x["category"] for x in s["mistakes"]], "top3": s["top3"],
                     "reviewed": bool(s["summary"])})
    mem = Memory(matches_dir)
    career = {"matches": rows[::-1], "habits": mem.top_habits(10), "lessons": mem.lessons,
              "grid": [{"col": c, "row": r, "n": n} for (c, r), n in grid.items()]}
    out = Path(matches_dir) / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_render("index.html", DATA=career), encoding="utf-8")
    return out
