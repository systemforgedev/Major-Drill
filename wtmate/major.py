"""Major: the deep tier. Slow, careful post-match review and improvement plans.

It reads Drill's frame-by-frame log plus key frames, weighs several
explanations for each death or bad moment, writes the debrief, grades
Drill's calls, and adds rules to Drill's lessons-learned file so Drill improves.
"""
from __future__ import annotations

import json

from .match import Match
from .memory import Memory
from .models import Image, Provider, Text
from .schema import DEBRIEF_SCHEMA, MISTAKES, PLAN_SCHEMA

SYSTEM = """You are Major, a patient War Thunder mentor reviewing one of the player's matches afterwards.
The player gets frustrated mid-match and finds it hard to remember what went wrong, so your job is
to find the few repeat mistakes that matter and explain them simply and kindly.

You get: a timeline written by Drill, the fast teammate model (one line per sampled frame), any game events,
the calls the fast model made, the player's history, and key frames (labelled with t in seconds).

Method:
1. Find the moments that decided the match: deaths, big hits taken, missed chances.
2. For each one, consider at least two competing explanations and mark each supported, rejected
   or unclear, citing what you saw (timestamp, minimap, kill feed). Don't guess beyond the evidence.
3. Tag each mistake with one category from: {cats}.
4. top3: the three things to change next match, most important first, each under 15 words.
5. good_plays: one to three things the player did well. Be specific.
6. call_grades: grade Drill's calls that mattered (right, wrong, too late, unclear),
   and say what it should have said instead.
7. lessons_updates: up to 3 short if-then rules for Drill's lessons-learned file that would have made its calls better.
   Only add rules supported by this match.
Times are seconds from the start of the recording."""


def _timeline(observations, events, calls) -> str:
    lines = ["t(s) | alive | situation | grid | event | threat | call (conf) | reason"]
    for o in observations:
        lines.append(f"{o['t']:.0f} | {'y' if o.get('alive') else 'n'} | {o.get('situation','')} | "
                     f"{o.get('minimap_grid','')} | {o.get('event','')} | {o.get('threat','')} | "
                     f"{o.get('call','')} ({o.get('confidence',0):.2f}) | {o.get('reason','')}")
    if events:
        lines.append("\nGame events (from the game's own local HUD feed):")
        lines += [f"{e['t']:.0f}s {e.get('type','')}: {e.get('msg','')}" for e in events]
    if calls:
        lines.append("\nCalls actually spoken live:")
        lines += [f"{c['t']:.0f}s \"{c['call']}\" ({c.get('reason','')})" for c in calls]
    return "\n".join(lines)


def pick_key_frames(match: Match, observations, events, limit: int = 24) -> list[tuple[float, bytes]]:
    frames = match.frames()
    if not frames:
        return []
    important = [o["t"] for o in observations if o.get("event") in ("death", "hit taken")]
    important += [e["t"] for e in events if e.get("type") in ("death", "hit_taken")]
    chosen: set[float] = set()
    times = [t for t, _ in frames]
    # Up to 3 frames leading into each important moment.
    for t0 in sorted(set(important)):
        before = [t for t in times if t0 - 15 <= t <= t0]
        chosen.update(before[-3:])
    # Fill the rest evenly so the whole match is covered.
    room = max(0, limit - len(chosen))
    if room:
        step = max(1, len(times) // room)
        chosen.update(times[::step][:room])
    picked = sorted(chosen)[:limit]
    lookup = dict(frames)
    return [(t, lookup[t].read_bytes()) for t in picked]


def debrief_match(match: Match, provider: Provider, memory: Memory, key_frames: int = 24) -> dict:
    observations = match.read("observations")
    events = match.read("events")
    calls = match.read("calls")
    parts = [Text("Player history:\n" + memory.prompt_block()),
             Text("Timeline:\n" + _timeline(observations, events, calls))]
    for t, jpeg in pick_key_frames(match, observations, events, key_frames):
        parts += [Text(f"key frame t={t:.1f}s"), Image(jpeg)]
    parts.append(Text("Write the debrief."))
    res = provider.complete_json(SYSTEM.format(cats=", ".join(MISTAKES)), parts, DEBRIEF_SCHEMA)
    debrief = res.data | {"_model": res.model, "_latency_s": round(res.latency_s, 1),
                          "_tokens": {"in": res.input_tokens, "out": res.output_tokens}}
    match.write_json("debrief.json", debrief)
    memory.record_debrief(match.id, debrief)
    return debrief


PLAN_SYSTEM = """You are Major, a patient War Thunder mentor. You now see the player's whole history:
every reviewed match, where they spent time and where they died (minimap grid squares), their repeat
mistakes, and Drill's current lessons-learned file.

Write an improvement plan:
- headline: the one thing holding them back most.
- death_patterns: where and why they keep dying. Only claim a pattern seen in 2+ matches.
- focus_areas: at most 3 habits for the next 3 to 5 matches, each with a concrete practice and a
  measure the app already tracks (deaths, mistake counts by category, time in each situation).
- progress: what changed across matches, with numbers. Say plainly if there is too little data.
- drill_lessons: rewrite Drill's lessons-learned list from scratch: keep rules that still matter,
  drop stale ones, add rules for the focus areas. Short if-then rules Drill can apply from one frame.
Be kind and concrete; the player gets frustrated easily and needs a clear next step, not a lecture."""


def plan_improvement(matches_dir, provider: Provider, memory: Memory) -> dict:
    """Major's cross-match plan. Rewrites Drill's lessons and writes plan.json."""
    from pathlib import Path

    from .review import all_matches
    from .stats import match_stats, parse_grid

    lines = []
    for m in all_matches(matches_dir):
        s = match_stats(m)
        if not s["summary"]:
            continue
        obs = {o["t"]: o for o in s["observations"]}
        death_grids = []
        for t in s["deaths"]:
            before = [o for tt, o in obs.items() if t - 20 <= tt <= t and parse_grid(o["grid"])]
            death_grids.append(before[-1]["grid"] if before else "?")
        top_sq = [f"{chr(65 + g['row'])}{g['col'] + 1}" for g in sorted(s["grid"], key=lambda g: -g["n"])[:3]]
        sits = [f"{k} {v:.0%}" for k, v in list(s["situations"].items())[:4]]
        cats = [x["category"] for x in s["mistakes"]]
        lines.append(
            f"Match {s['id']}: {s['duration_s']/60:.0f} min, kills {len(s['kills'])}, deaths {len(s['deaths'])} "
            f"(died in: {', '.join(death_grids) or 'none'}); most time in "
            f"{', '.join(top_sq) or 'unknown'}; mistakes: {', '.join(cats) or 'none'}; "
            f"situations: {', '.join(sits)}")
    if not lines:
        raise RuntimeError("No reviewed matches yet. Run a debrief on at least one match first.")
    parts = [Text("History, oldest first:\n" + "\n".join(lines)),
             Text("Habit counts and Drill's current lessons:\n" + memory.prompt_block()),
             Text("Write the plan.")]
    res = provider.complete_json(PLAN_SYSTEM, parts, PLAN_SCHEMA)
    plan = res.data | {"_model": res.model, "_matches": len(lines)}
    memory.set_lessons(plan.get("drill_lessons", []))
    out = Path(matches_dir) / "_profile" / "plan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return plan
