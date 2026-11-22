"""Local Drill: protocols + HUD readers, plus an optional local vision model.

No API key, no internet. Three ways to run, from cheapest to richest:

1. Rules only: HUD detectors read numbers and colours off the screen, the
   protocol engine picks the call. Runs on any PC in a few milliseconds.
2. Rules + a local vision model ("kev", or any model served by Ollama or
   LM Studio): the model only describes the frame (situation, where the
   enemies are). It never picks the call; the protocols still do.
3. Cloud (optional, later): the original Claude-based Drill, `drill = "model"`.

Every time a protocol fires, the frame and the facts are saved to
firings.jsonl so you can mark each one right or wrong (`wtmate label`).
Those labels are the training data for a small local model later on.
"""
from __future__ import annotations

import json
from pathlib import Path

from .hud import HudReader
from .match import Match
from .models import Image, Provider, Text
from .profiles import GameProfile
from .protocols import Engine, ProtocolSet

VISION_SYSTEM = """You describe one screenshot of {game} for a rules engine. You do not give advice.
Report only what is visible. If you can't tell, use the safest answer ("unclear", 0, false).

How to read the screen:
{screen_guide}
{extra}
Fields:
- situation: one of the listed situations.
- alive: false only on a death, mission failed or respawn screen.
- enemies_on_screen: how many enemies you can see in the main view.
- threat_side: where most nearby enemies are relative to the player's mech
  (screen up = front): none, left, right, front, behind or all around.
- heavy_enemy: true if a big or boss enemy is visible.
- player_moving: true if the player's mech seems to be moving (motion trails, camera shift), else false.
- in_menu: true for menus, loadout, research, loading or full-screen results.
- threat: under 8 words, the biggest visible threat, or empty."""


def vision_schema(profile: GameProfile) -> dict:
    props = {
        "situation": {"type": "string", "enum": profile.situations},
        "alive": {"type": "boolean"},
        "enemies_on_screen": {"type": "integer"},
        "threat_side": {"type": "string", "enum": ["none", "left", "right", "front", "behind", "all around"]},
        "heavy_enemy": {"type": "boolean"},
        "player_moving": {"type": "boolean"},
        "in_menu": {"type": "boolean"},
        "threat": {"type": "string"},
    }
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


class LocalDrill:
    """One frame in, one observation out (same shape as the model Drill's)."""

    def __init__(self, profile: GameProfile, pset: ProtocolSet, vision: Provider | None = None):
        self.profile, self.pset, self.vision = profile, pset, vision
        self.hud = HudReader(pset.detectors)
        self.engine = Engine(pset)
        self.vision_errors = 0

    def facts(self, jpeg: bytes) -> dict:
        facts = self.hud.read(jpeg)
        if self.vision is not None:
            try:
                system = VISION_SYSTEM.format(game=self.profile.title, screen_guide=self.profile.screen_guide,
                                              extra=self.pset.vision.extra)
                res = self.vision.complete_json(system, [Image(jpeg), Text("Describe this frame.")],
                                                vision_schema(self.profile))
                # The HUD readers are exact, so they win where both have a value.
                facts = {k: (v.lower() if isinstance(v, str) else v) for k, v in res.data.items()} | facts
                facts["_vision_s"] = round(res.latency_s, 2)
            except Exception as e:  # a slow or broken model must never stop the rules
                self.vision_errors += 1
                if self.vision_errors <= 3:
                    print("[drill] vision model error (rules keep running):", e)
        return facts

    def observe(self, t: float, jpeg: bytes) -> dict:
        d = self.engine.decide(t, self.facts(jpeg))
        f = d.facts
        top = d.top
        return {
            "t": t,
            "alive": bool(f.get("alive", True)),
            "situation": d.situation or "unclear",
            "minimap_grid": "",
            "threat": str(f.get("threat", "") or (top.why if top else "")),
            "event": d.events[0] if d.events else "none",
            "hypotheses": [],
            "call": d.call,
            "say": d.say,
            "confidence": 1.0 if top else 0.0,  # rules either fire or they don't
            "reason": top.why if top else "",
            "protocol": top.id if top else "",
            "fired": [p.id for p in d.fired],
            "facts": {k: v for k, v in f.items() if not k.startswith("_")},
        }


def log_firing(match: Match, obs: dict, jpeg: bytes):
    """Save the frame and facts behind every protocol firing, for labelling later."""
    if not obs.get("fired"):
        return
    folder = match.root / "firings"
    folder.mkdir(exist_ok=True)
    img = folder / f"t{obs['t']:08.1f}.jpg"
    img.write_bytes(jpeg)
    for pid in obs["fired"]:
        match.append("firings", {"t": obs["t"], "protocol": pid, "spoken": pid == obs.get("protocol"),
                                 "frame": f"firings/{img.name}", "facts": obs.get("facts", {}),
                                 "label": None, "note": ""})


def observe_match_local(match: Match, drill: LocalDrill, progress=None) -> dict:
    """Run the local Drill over every frame of a recording. Writes observations.jsonl."""
    for name in ("observations", "firings"):
        p = match.root / f"{name}.jsonl"
        if p.exists():
            p.unlink()
    frames = match.frames()
    calls = 0
    for i, (t, path) in enumerate(frames):
        jpeg = Path(path).read_bytes()
        o = drill.observe(t, jpeg)
        match.append("observations", o)
        log_firing(match, o, jpeg)
        calls += o["call"] != "none"
        if progress:
            progress(i + 1, len(frames))
    stats = {"frames": len(frames), "calls": calls, "mode": "protocols",
             "vision": bool(drill.vision), "ocr": drill.hud.ocr, "skipped_detectors": drill.hud.skipped}
    match.write_meta({"fast_stats": stats})
    return stats


def label_firings(match: Match, ask=input, show=None) -> dict:
    """Walk through unlabelled firings: right (y), wrong (n), skip (s), quit (q)."""
    rows = match.read("firings")
    done = {"right": 0, "wrong": 0}
    for r in rows:
        if r.get("label") is not None:
            continue
        if show:
            show(match.root / r["frame"])
        ans = ask(f"t={r['t']:.0f}s {r['protocol']} (spoken: {r['spoken']}) - right? [y/n/s/q] ").strip().lower()
        if ans.startswith("q"):
            break
        if ans.startswith("y"):
            r["label"] = "right"
        elif ans.startswith("n"):
            r["label"] = "wrong"
            r["note"] = ask("  what should it have been? (optional) ").strip()
        else:
            continue
        done[r["label"]] += 1
    (match.root / "firings.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return done
