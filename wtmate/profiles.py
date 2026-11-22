"""Game profiles: everything game-specific lives here, so the same Drill and
Major work for any game. Pick one with `game = "..."` in wtmate.toml, or point
`game` at your own TOML file with the same keys (see profiles/example_game.toml).
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GameProfile:
    key: str
    title: str
    teammate: str          # how Drill sees itself, e.g. "squadmate" or "co-pilot"
    screen_guide: str      # how to read a frame of this game
    calls: list[str]       # short things Drill may say; first must be "none"
    situations: list[str]
    events: list[str]      # first must be "none"; include "death" so deaths can be counted
    mistakes: list[str]    # categories Major tags; keep "other" last
    grid_hint: str = "Grid square of the player on the minimap, like 'D4'. Empty if there is no minimap or it is unreadable."
    notes: list[str] = field(default_factory=list)

    def check(self):
        assert self.calls and self.calls[0] == "none", "calls must start with 'none'"
        assert self.events and self.events[0] == "none", "events must start with 'none'"
        assert "death" in self.events, "events must include 'death'"
        return self


WAR_THUNDER = GameProfile(
    key="war_thunder",
    title="War Thunder (ground battles)",
    teammate="squadmate",
    screen_guide="""- Minimap (usually a corner): the player's arrow and grid square (letters are rows, numbers columns), red enemy markers, capture points.
- Kill feed and hit messages: deaths, kills, the player's own damage.
- The 3D view: cover, open ground, visible enemies, whether the player is moving.
- A respawn or vehicle-select screen means the player is dead or spectating.""",
    calls=["none", "check minimap", "flank left", "flank right", "pull back", "hold position",
           "push now", "change position", "angle your armor", "cap the point"],
    situations=["spawning", "driving to position", "holding position", "in a firefight", "flanking",
                "retreating", "capping", "dead or spectating", "menu or loading", "unclear"],
    events=["none", "death", "kill", "hit taken", "hit dealt", "capture", "respawn"],
    mistakes=["ignored minimap threat", "pushed alone", "stayed in one spot too long", "exposed weak armor",
              "bad route or open ground", "overextended after a kill", "slow to retreat when hurt",
              "missed the objective", "poor target choice", "other"],
)

# A starting point for single-player action games (shooters, action RPGs,
# soulslikes). Good enough to prove the concept; a game-specific profile is better.
GENERIC_ACTION = GameProfile(
    key="generic_action",
    title="Any single-player action game",
    teammate="co-op partner",
    screen_guide="""- Health, shield, stamina and ammo bars: how close the player is to dying or running dry.
- Minimap or compass if there is one: objectives and enemy markers.
- The main view: enemies, cover, hazards, whether the player is moving or standing still.
- Death, game-over or loading screens mean the player died or is between attempts.""",
    calls=["none", "back off", "heal up", "reload now", "take cover", "watch your flank",
           "dodge", "focus the closest enemy", "slow down", "go for the objective"],
    situations=["exploring", "in combat", "boss fight", "low health", "healing or resting",
                "in a menu or cutscene", "dead or loading", "unclear"],
    events=["none", "death", "kill", "big hit taken", "checkpoint", "objective done"],
    mistakes=["fought at low health", "got surrounded", "ran out of ammo or resources", "greedy attacks",
              "ignored the warning sign", "wrong target first", "stood in a hazard",
              "rushed into an unknown area", "other"],
    grid_hint="Grid square on the minimap if it has one, like 'D4'. Usually empty for games without a grid.",
)

BUILTIN = {p.key: p for p in (WAR_THUNDER, GENERIC_ACTION)}


def load_profile(name_or_path: str) -> GameProfile:
    if name_or_path in BUILTIN:
        return BUILTIN[name_or_path]
    path = Path(name_or_path)
    if path.exists():
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
        data.setdefault("key", path.stem)
        return GameProfile(**data).check()
    raise ValueError(f"Unknown game profile {name_or_path!r}. Built in: {', '.join(BUILTIN)}; or give a .toml path.")
