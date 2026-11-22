"""Local Major: a no-AI debrief built from what the protocols saw.

It counts how often each protocol fired, turns protocols tagged with a
`mistake` into the match's mistakes, and uses their `tip` text for the
three things to fix next time. Same debrief.json shape as the Claude Major,
so the review and career pages work unchanged.

For a deeper review, upload the recording to a Claude chat and ask for new or
better protocols (see PROTOCOLS.md); no API key is needed for that.
"""
from __future__ import annotations

from collections import Counter

from .match import Match
from .memory import Memory
from .protocols import ProtocolSet

EPISODE_GAP_S = 15.0  # firings closer than this count as one moment


def _episodes(times: list[float]) -> list[float]:
    out = []
    for t in sorted(times):
        if not out or t - out[-1][-1] > EPISODE_GAP_S:
            out.append([t])
        else:
            out[-1].append(t)
    return [e[0] for e in out]


def local_debrief(match: Match, pset: ProtocolSet, memory: Memory) -> dict:
    obs = match.read("observations")
    by_id = {p.id: p for p in pset.protocols}
    fired: dict[str, list[float]] = {}
    for o in obs:
        for pid in o.get("fired", []):
            fired.setdefault(pid, []).append(o["t"])
    episodes = {pid: _episodes(ts) for pid, ts in fired.items()}

    mistakes, counts = [], Counter()
    for pid, starts in episodes.items():
        p = by_id.get(pid)
        if not p or not p.mistake:
            continue
        counts[pid] = len(starts)
        for t in starts:
            mistakes.append({"t": t, "category": p.mistake, "what_happened": p.why or p.id,
                             "better_option": p.tip or f"Listen for \"{p.say or p.call}\".",
                             "hypotheses_checked": [], "protocol": pid})
    mistakes.sort(key=lambda m: m["t"])
    top3 = [by_id[pid].tip or by_id[pid].why for pid, _ in counts.most_common(3)]
    good = [by_id[pid].good for pid in episodes if by_id.get(pid) and by_id[pid].good]
    if not mistakes:
        good.append("No mistake protocols fired. Either a clean run, or the protocols need more rules.")

    spoken = Counter(o["call"] for o in obs if o.get("call", "none") != "none")
    deaths = sum(1 for o in obs if o.get("event") == "death")
    minutes = (obs[-1]["t"] / 60) if obs else 0
    worst = ", ".join(f"{by_id[pid].mistake} x{n}" for pid, n in counts.most_common(3)) or "none"
    summary = (f"{minutes:.0f} minutes reviewed by the protocols ({len(pset.protocols)} rules). "
               f"Drill made {sum(spoken.values())} calls; deaths seen: {deaths}. Repeat mistakes: {worst}.")
    debrief = {"summary": summary, "mistakes": mistakes, "top3": top3, "good_plays": good[:3],
               "call_grades": [], "lessons_updates": [],
               "protocol_counts": {pid: len(s) for pid, s in episodes.items()},
               "_model": "local protocols"}
    match.write_json("debrief.json", debrief)
    memory.record_debrief(match.id, debrief)
    return debrief
