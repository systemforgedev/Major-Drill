"""Optional: War Thunder's own local web map (http://127.0.0.1:8111).

The game serves this itself for its browser map feature. It shows the same
things as the in-game minimap and kill feed, nothing hidden. A Gaijin
community manager said in 2024 that overlays using this localhost data are
not a bannable offense, but ESP-style enemy markers are not approved, so this
module only logs YOUR position and the kill feed. It never reads game memory
and never sends input.
"""
from __future__ import annotations

import json
import re
import urllib.request

KILL_RE = re.compile(
    r"^(?P<killer>.+?)\s*\((?P<kv>[^)]*)\)\s+(?P<verb>destroyed|shot down|set afire|has destroyed)\s+(?P<victim>.+?)(?:\s*\((?P<vv>[^)]*)\))?\s*$")


class Telemetry:
    def __init__(self, url: str = "http://127.0.0.1:8111", timeout: float = 0.5):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.last_dmg = 0

    def _get(self, path: str):
        with urllib.request.urlopen(self.url + path, timeout=self.timeout) as r:
            return r.read()

    def _json(self, path: str):
        return json.loads(self._get(path))

    def available(self) -> bool:
        try:
            self._get("/map_info.json")
            return True
        except Exception:
            return False

    def in_match(self) -> bool:
        try:
            return bool(self._json("/map_info.json").get("valid"))
        except Exception:
            return False

    def map_info(self) -> dict:
        return self._json("/map_info.json")

    def player(self) -> dict | None:
        try:
            return find_player(self._json("/map_obj.json"))
        except Exception:
            return None

    def save_map(self, path) -> bool:
        try:
            data = self._get("/map.img")
            if data:
                with open(path, "wb") as fh:
                    fh.write(data)
                return True
        except Exception:
            pass
        return False

    def new_feed(self) -> list[dict]:
        """Kill-feed lines since the last call."""
        try:
            data = self._json(f"/hudmsg?lastEvt=0&lastDmg={self.last_dmg}")
        except Exception:
            return []
        out = []
        for d in data.get("damage", []):
            self.last_dmg = max(self.last_dmg, int(d.get("id", 0)))
            out.append(d)
        return out


def find_player(objs: list[dict]) -> dict | None:
    for o in objs:
        if o.get("icon") == "Player" and "x" in o and "y" in o:
            return {"x": float(o["x"]), "y": float(o["y"]),
                    "dx": float(o.get("dx", 0)), "dy": float(o.get("dy", 0))}
    return None


def classify_feed(msg: str, player_name: str) -> str | None:
    """'kill' if the player destroyed someone, 'death' if the player was destroyed."""
    if not player_name:
        return None
    m = KILL_RE.match(msg.strip())
    if not m:
        return None
    name = player_name.lower()
    if name in m.group("killer").lower():
        return "kill"
    if name in m.group("victim").lower():
        return "death"
    return None
