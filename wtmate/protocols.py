"""Protocols: plain-English if-then rules that decide what Drill says.

A protocol file (one per game, TOML) holds two lists:

  [[detector]]  how to read facts off the screen (see hud.py)
  [[protocol]]  situation -> call, with a priority

Example protocol:

  [[protocol]]
  id = "low-hp-in-a-fight"
  priority = 1                       # 1 = most important; lower number wins
  when = ["hp_pct < 0.35", "enemies_total >= 1"]   # all must be true
  call = "back off"                  # one of the game profile's calls
  say = "Back off, you're low"       # what Drill says out loud (default: the call)
  why = "Low HP with enemies on the minimap"
  mistake = "fought at low health"   # optional: counted in the local review
  tip = "When HP drops under a third, back off and let the call-ins work."
  hold_s = 0                         # the condition must stay true this long first
  cooldown_s = 20                    # don't fire this protocol again within this window

Conditions are `fact OP value` (OP is < <= > >= == !=, value is a number,
true/false, a quoted string or another fact), or just `fact` / `not fact`.
`when_any` is the same but only one needs to be true. A fact nobody could read
(no OCR installed, no vision model) makes its condition false, so a protocol
never fires on a guess.

Facts come from the HUD detectors, from an optional local vision model, and
from the engine itself: `t`, and `d_<fact>` (how much a number changed over the
last ~3 seconds, e.g. `d_hp < -60` means a big hit).
"""
from __future__ import annotations

import operator
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .hud import Detector

OPS = {"<=": operator.le, ">=": operator.ge, "==": operator.eq, "!=": operator.ne,
       "<": operator.lt, ">": operator.gt}
_COND = re.compile(r"^\s*([A-Za-z_][\w]*)\s*(<=|>=|==|!=|<|>)\s*(.+?)\s*$")
_NAME = re.compile(r"^[A-Za-z_]\w*$")
_MISSING = object()
DELTA_WINDOW_S = 3.0


class ProtocolError(ValueError):
    pass


@dataclass
class Condition:
    text: str
    fact: str
    op: str | None = None        # None means a bare `fact` / `not fact`
    value: object = None
    value_is_fact: bool = False
    negate: bool = False

    @classmethod
    def parse(cls, text: str) -> "Condition":
        m = _COND.match(text)
        if m:
            fact, op, raw = m.groups()
            raw = raw.strip()
            if raw.lower() in ("true", "false"):
                return cls(text, fact, op, raw.lower() == "true")
            if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
                return cls(text, fact, op, raw[1:-1].lower())
            try:
                return cls(text, fact, op, float(raw))
            except ValueError:
                pass
            if _NAME.match(raw):
                return cls(text, fact, op, raw, value_is_fact=True)
            raise ProtocolError(f"can't read the value in condition {text!r}")
        words = text.split()
        if len(words) == 2 and words[0] == "not" and _NAME.match(words[1]):
            return cls(text, words[1], negate=True)
        if len(words) == 1 and _NAME.match(words[0]):
            return cls(text, words[0])
        raise ProtocolError(f"can't read condition {text!r}. Use `fact < 3`, `fact == \"text\"`, `fact` or `not fact`.")

    def holds(self, facts: dict) -> bool:
        v = facts.get(self.fact, _MISSING)
        if v is _MISSING or v is None:
            return False  # unknown is never true
        if self.op is None:
            return (not bool(v)) if self.negate else bool(v)
        other = facts.get(self.value, _MISSING) if self.value_is_fact else self.value
        if other is _MISSING or other is None:
            return False
        if isinstance(v, str):
            v = v.lower()
        try:
            if isinstance(other, bool) or isinstance(v, bool):
                return OPS[self.op](bool(v), bool(other))
            if isinstance(other, float) and not isinstance(v, (int, float)):
                return False
            return bool(OPS[self.op](v, other))
        except TypeError:
            return False


@dataclass
class Protocol:
    id: str
    call: str = "none"
    priority: int = 5
    when: list[str] = field(default_factory=list)
    when_any: list[str] = field(default_factory=list)
    say: str = ""
    why: str = ""
    situation: str = ""        # label for the timeline (one of the profile's situations)
    event: str = ""            # event to log when it starts firing (one of the profile's events)
    mistake: str = ""          # mistake category to count in the local review
    tip: str = ""              # the fix, shown in the review's top 3
    good: str = ""             # a good play to praise in the review
    hold_s: float = 0.0
    cooldown_s: float = 20.0
    enabled: bool = True
    source: str = ""           # where it came from, e.g. "review of 2026-11-22 run"

    def __post_init__(self):
        if not self.when and not self.when_any:
            raise ProtocolError(f"protocol {self.id!r} needs `when` or `when_any`")
        self._all = [Condition.parse(c) for c in self.when]
        self._any = [Condition.parse(c) for c in self.when_any]

    def matches(self, facts: dict) -> bool:
        if self._all and not all(c.holds(facts) for c in self._all):
            return False
        if self._any and not any(c.holds(facts) for c in self._any):
            return False
        return True

    @property
    def facts_used(self) -> set[str]:
        out = set()
        for c in self._all + self._any:
            out.add(c.fact)
            if c.value_is_fact:
                out.add(c.value)
        return out


@dataclass
class VisionCfg:
    """What to ask a local vision model (kev) for, if one is switched on."""
    extra: str = ""            # game-specific hints added to the question


@dataclass
class ProtocolSet:
    game: str
    protocols: list[Protocol]
    detectors: list[Detector]
    derived: dict = field(default_factory=dict)  # name -> "a / b" style formulas
    vision: VisionCfg = field(default_factory=VisionCfg)
    path: str = ""

    def validate(self, profile) -> list[str]:
        """Problems that would make protocols silently useless. Empty list = fine."""
        problems = []
        ids = [p.id for p in self.protocols]
        for dup in {i for i in ids if ids.count(i) > 1}:
            problems.append(f"protocol id {dup!r} is used twice")
        for p in self.protocols:
            if p.call not in profile.calls:
                problems.append(f"{p.id}: call {p.call!r} is not one of the game's calls {profile.calls}")
            if p.situation and p.situation not in profile.situations:
                problems.append(f"{p.id}: situation {p.situation!r} is not one of {profile.situations}")
            if p.event and p.event not in profile.events:
                problems.append(f"{p.id}: event {p.event!r} is not one of {profile.events}")
            if p.mistake and p.mistake not in profile.mistakes:
                problems.append(f"{p.id}: mistake {p.mistake!r} is not one of {profile.mistakes}")
        return problems

    def known_facts(self) -> set[str]:
        out = {"t", "alive"} | set(self.derived) | set(VISION_FACTS)
        for d in self.detectors:
            if d.type == "blips":
                out |= {f"{d.name}_{k}" for k in ("left", "right", "front", "behind", "total")}
            else:
                out.add(d.name)
            if d.threshold is not None:
                out.add(d.flag or f"{d.name}_on")
        return out | {f"d_{f}" for f in out}


# Facts a local vision model is asked for (see local.py). Same for every game.
VISION_FACTS = ("situation", "alive", "enemies_on_screen", "threat_side", "heavy_enemy",
                "player_moving", "in_menu", "threat")


def load_protocols(path: str | Path) -> ProtocolSet:
    path = Path(path)
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    unknown = set(data) - {"game", "protocol", "detector", "derived", "vision"}
    if unknown:
        raise ProtocolError(f"{path.name}: unknown sections {sorted(unknown)}")
    try:
        protocols = [Protocol(**p) for p in data.get("protocol", [])]
        detectors = [Detector(**d).check() for d in data.get("detector", [])]
        vision = VisionCfg(**data.get("vision", {}))
    except TypeError as e:
        raise ProtocolError(f"{path.name}: {e}") from e
    derived = dict(data.get("derived", {}))
    for name, formula in derived.items():
        _parse_formula(formula)  # fail early on typos
    return ProtocolSet(data.get("game", path.stem), protocols, detectors, derived, vision, str(path))


_FORMULA = re.compile(r"^\s*([A-Za-z_]\w*|\d+(?:\.\d+)?)\s*([-+*/])\s*([A-Za-z_]\w*|\d+(?:\.\d+)?)\s*$")


def _parse_formula(text: str):
    m = _FORMULA.match(text)
    if not m:
        raise ProtocolError(f"derived formula {text!r} must look like `a / b` (one of + - * /)")
    return m.groups()


def _operand(tok, facts):
    if _NAME.match(tok):
        return facts.get(tok)
    return float(tok)


@dataclass
class Decision:
    t: float
    facts: dict
    fired: list[Protocol]          # every protocol whose condition held (after hold_s, cooldown)
    matching: list[Protocol]       # every protocol whose condition held right now
    call: str = "none"
    say: str = ""
    top: Protocol | None = None
    events: list[str] = field(default_factory=list)
    situation: str = ""


class Engine:
    """Turns facts into a decision. Keeps a little memory: how long each
    protocol has been true, when it last fired, and recent values for d_<fact>."""

    def __init__(self, pset: ProtocolSet):
        self.pset = pset
        self.protocols = sorted([p for p in pset.protocols if p.enabled], key=lambda p: p.priority)
        self.true_since: dict[str, float] = {}
        self.last_fired: dict[str, float] = {}
        self.history: list[tuple[float, dict]] = []
        self.max_seen: dict[str, float] = {}

    def enrich(self, t: float, facts: dict) -> dict:
        facts = dict(facts)
        facts["t"] = t
        # Running maximum for every number, so `hp / hp_max` works without knowing the mech's max HP.
        for k, v in list(facts.items()):
            if isinstance(v, (int, float)) and not isinstance(v, bool) and k != "t":
                self.max_seen[k] = max(self.max_seen.get(k, v), v)
                facts[f"{k}_max"] = self.max_seen[k]
        for name, formula in self.pset.derived.items():
            a, op, b = _parse_formula(formula)
            x, y = _operand(a, facts), _operand(b, facts)
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                if op == "/" and y == 0:
                    continue
                facts[name] = round({"+": x + y, "-": x - y, "*": x * y, "/": x / y if y else 0}[op], 4)
        past = [f for (tt, f) in self.history if t - tt >= DELTA_WINDOW_S]
        if past:
            old = past[-1]
            for k, v in list(facts.items()):
                if isinstance(v, (int, float)) and not isinstance(v, bool) and isinstance(old.get(k), (int, float)) \
                        and not isinstance(old.get(k), bool) and k != "t":
                    facts[f"d_{k}"] = round(v - old[k], 4)
        self.history.append((t, facts))
        self.history = [(tt, f) for tt, f in self.history if t - tt <= DELTA_WINDOW_S * 3]
        return facts

    def decide(self, t: float, raw_facts: dict) -> Decision:
        facts = self.enrich(t, raw_facts)
        matching, fired, events = [], [], []
        for p in self.protocols:
            if not p.matches(facts):
                self.true_since.pop(p.id, None)
                continue
            matching.append(p)
            started = p.id not in self.true_since
            since = self.true_since.setdefault(p.id, t)
            if t - since < p.hold_s:
                continue
            if t - self.last_fired.get(p.id, -1e9) < p.cooldown_s:
                continue
            fired.append(p)
            self.last_fired[p.id] = t
            if p.event and (started or p.hold_s):
                events.append(p.event)
        d = Decision(t, facts, fired, matching, events=events)
        speaking = [p for p in fired if p.call != "none"]
        if speaking:
            d.top = speaking[0]  # already sorted by priority
            d.call, d.say = d.top.call, d.top.say or d.top.call
        labelled = [p for p in matching if p.situation]
        d.situation = labelled[0].situation if labelled else str(facts.get("situation", "") or "")
        return d
