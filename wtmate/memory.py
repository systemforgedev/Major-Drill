"""Habit memory: what you keep doing wrong across matches, plus Drill's
lessons-learned file: short rules that Major writes for Drill."""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

MAX_RULES = 15


class Memory:
    def __init__(self, matches_dir: str | Path):
        self.path = Path(matches_dir) / "_profile" / "memory.json"
        self.data = {"matches": [], "mistake_counts": {}, "lessons": [], "updated": None}
        if self.path.exists():
            self.data.update(json.loads(self.path.read_text(encoding="utf-8")))

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data["updated"] = time.time()
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    @property
    def lessons(self) -> list[str]:
        return list(self.data["lessons"])

    def top_habits(self, n: int = 5) -> list[tuple[str, int]]:
        return Counter(self.data["mistake_counts"]).most_common(n)

    def record_debrief(self, match_id: str, debrief: dict):
        if match_id in {m["id"] for m in self.data["matches"]}:
            return  # already counted; re-running a debrief must not double count
        cats = [m["category"] for m in debrief.get("mistakes", [])]
        counts = Counter(self.data["mistake_counts"])
        counts.update(cats)
        self.data["mistake_counts"] = dict(counts)
        self.data["matches"].append({"id": match_id, "mistakes": cats,
                                     "top3": debrief.get("top3", []), "t": time.time()})
        # Newest rules first, de-duplicated, capped so the fast prompt stays short.
        rules = [r.strip() for r in debrief.get("lessons_updates", []) if r.strip()]
        merged = []
        for r in rules + self.data["lessons"]:
            if r.lower() not in {m.lower() for m in merged}:
                merged.append(r)
        self.data["lessons"] = merged[:MAX_RULES]
        self.save()

    def set_lessons(self, rules: list[str]):
        """Major's plan can rewrite the whole list (it sees every match at once)."""
        self.data["lessons"] = [r.strip() for r in rules if r.strip()][:MAX_RULES]
        self.save()

    def prompt_block(self) -> str:
        lines = []
        habits = self.top_habits()
        if habits:
            lines.append("This player's repeat mistakes so far (count across matches): "
                         + "; ".join(f"{c} x{n}" for c, n in habits))
        if self.lessons:
            lines.append("Lessons learned from Major's past reviews (follow these):")
            lines += [f"- {r}" for r in self.lessons]
        return "\n".join(lines) or "No history yet: this is one of the first matches."
