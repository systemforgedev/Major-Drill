import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from wtmate.hud import Detector, HudReader
from wtmate.live import CallGate
from wtmate.local import LocalDrill, label_firings
from wtmate.local_major import local_debrief
from wtmate.match import Match
from wtmate.memory import Memory
from wtmate.profiles import load_profile
from wtmate.protocols import Condition, Engine, Protocol, ProtocolError, ProtocolSet, load_protocols

ROOT = Path(__file__).parent.parent
HUD = Path(__file__).parent / "fixtures" / "mech_havoc_hud.jpg"
MECH = load_profile(str(ROOT / "profiles" / "mech_havoc.toml"))
MECH_PROTOCOLS = ROOT / "protocols" / "mech_havoc.toml"


def test_conditions():
    f = {"hp": 50.0, "side": "right", "ready": True, "zero": 0, "a": 3, "b": 2}
    assert Condition.parse("hp < 60").holds(f)
    assert not Condition.parse("hp >= 60").holds(f)
    assert Condition.parse("side == 'Right'").holds(f)
    assert Condition.parse("ready").holds(f) and not Condition.parse("not ready").holds(f)
    assert Condition.parse("not zero").holds(f)
    assert Condition.parse("a > b").holds(f)
    assert Condition.parse("ready == true").holds(f)
    # Unknown facts are never true, in either direction.
    assert not Condition.parse("missing < 5").holds(f)
    assert not Condition.parse("not missing").holds(f)
    assert not Condition.parse("hp > missing").holds(f)
    assert not Condition.parse("side < 3").holds(f)
    with pytest.raises(ProtocolError):
        Condition.parse("hp <<< 3")
    with pytest.raises(ProtocolError):
        Protocol(id="x", call="none")


def _set(*protocols, derived=None):
    return ProtocolSet("t", list(protocols), [], derived or {})


def test_priority_hold_and_cooldown():
    low = Protocol(id="low", call="back off", priority=1, when=["hp < 30"], cooldown_s=10)
    flank = Protocol(id="flank", call="watch your flank", priority=2, when=["right >= 1"], cooldown_s=10)
    still = Protocol(id="still", call="keep moving", priority=3, when=["moving == false"], hold_s=4, cooldown_s=0)
    e = Engine(_set(still, flank, low))
    d = e.decide(0, {"hp": 20, "right": 2, "moving": False})
    assert d.call == "back off" and [p.id for p in d.fired] == ["low", "flank"]  # priority 1 wins
    d = e.decide(2, {"hp": 20, "right": 2, "moving": False})
    assert d.call == "none"  # both cooling down, still not held 4 s yet
    d = e.decide(4, {"hp": 90, "right": 0, "moving": False})
    assert d.call == "keep moving"
    d = e.decide(5, {"hp": 90, "right": 0, "moving": True})
    d = e.decide(6, {"hp": 90, "right": 0, "moving": False})
    assert d.call == "none"  # hold timer restarted


def test_derived_running_max_and_deltas():
    big_hit = Protocol(id="hit", call="keep moving", when=["d_hp_pct < -0.2"], event="big hit taken")
    low = Protocol(id="low", call="back off", when=["hp_pct < 0.35"])
    e = Engine(_set(big_hit, low, derived={"hp_pct": "hp / hp_max"}))
    assert e.decide(0, {"hp": 400}).call == "none"
    assert e.decide(1.5, {"hp": 380}).call == "none"
    d = e.decide(3.5, {"hp": 200})  # lost half within ~3 s
    assert d.facts["hp_pct"] == 0.5 and d.call == "keep moving" and d.events == ["big hit taken"]
    assert e.decide(10, {"hp": 100}).call == "back off"


def _synthetic_frame():
    img = np.zeros((360, 640, 3), dtype=np.uint8)
    img[10:20, 10:110] = 255             # bar, full from 10 to 110 of 0..200
    img[100:110, 500:510] = [200, 0, 0]  # red blip right of the minimap centre
    img[60:66, 450:456] = [200, 0, 0]    # red blip left-and-up: more left than up
    img[150:156, 460:466] = [200, 0, 0]  # behind
    return img


def test_hud_readers():
    box = [400 / 640, 0, 600 / 640, 200 / 360]  # minimap 200x200, centre (500, 100)
    r = HudReader([
        Detector("bar", "bar", [0, 10 / 360, 200 / 640, 20 / 360], colour=[255, 255, 255], tolerance=10,
                 threshold=0.4, flag="bar_ok"),
        Detector("enemies", "blips", box, colour=[200, 0, 0], tolerance=20),
        Detector("red", "colour_share", box, colour=[200, 0, 0], tolerance=20),
        Detector("move", "change", [0, 0, 1, 1]),
        Detector("hp", "ocr_number", [0, 0, 0.1, 0.1]),
    ])
    f = r.read(_synthetic_frame())
    assert 0.45 <= f["bar"] <= 0.55 and f["bar_ok"]
    assert (f["enemies_right"], f["enemies_left"], f["enemies_behind"], f["enemies_total"]) == (1, 1, 1, 3)
    assert f["red"] > 0 and f["move"] == 0.0
    assert r.read(np.full((360, 640, 3), 128, dtype=np.uint8))["move"] > 0.3
    if not r.ocr:
        assert "hp" not in f and r.skipped == ["hp"]
    with pytest.raises(ValueError):
        Detector("x", "nope", [0, 0, 1, 1]).check()
    with pytest.raises(ValueError):
        Detector("x", "bar", [0.5, 0, 0.2, 1]).check()


def test_mech_havoc_protocols_on_real_hud():
    """Ivan's in-mission screenshot: one enemy right on the minimap, extraction open, call-ins ready."""
    pset = load_protocols(MECH_PROTOCOLS)
    assert pset.validate(MECH) == []
    drill = LocalDrill(MECH, pset)
    o = drill.observe(0.0, HUD.read_bytes())
    f = o["facts"]
    assert f["in_mission"] and f["extraction_available"] and f["mortar_ready"] and f["turret_ready"]
    assert f["enemies_right"] == 1 and f["enemies_total"] == 1
    assert o["call"] == "watch your flank" and o["say"] == "Enemies on your right flank"
    assert "extraction-open" in o["fired"] and o["event"] == "extraction available"
    # A plain black frame is not a mission.
    buf = Image.new("RGB", (1280, 720)).tobytes()
    blank = Image.frombytes("RGB", (1280, 720), buf)
    import io
    b = io.BytesIO()
    blank.save(b, "JPEG")
    o = drill.observe(1.5, b.getvalue())
    assert o["call"] == "none" and o["situation"] == "in a menu or loadout screen"


def test_protocol_file_validation(tmp_path):
    p = tmp_path / "p.toml"
    p.write_text('[[protocol]]\nid = "a"\nwhen = ["x"]\ncall = "dance"\nmistake = "nope"\n')
    probs = load_protocols(p).validate(MECH)
    assert any("dance" in s for s in probs) and any("nope" in s for s in probs)
    p.write_text('[[protocl]]\nid = "a"\n')
    with pytest.raises(ProtocolError):
        load_protocols(p)
    p.write_text('[derived]\nx = "a ** b"\n')
    with pytest.raises(ProtocolError):
        load_protocols(p)


def test_urgent_calls_skip_the_quiet_gap():
    g = CallGate(min_gap_s=6, repeat_gap_s=20, min_confidence=0.6, max_latency_s=3)
    assert g.decide({"call": "watch your flank", "confidence": 1.0}, 0, 0.1) == (True, "ok")
    assert g.decide({"call": "keep moving", "confidence": 1.0}, 2, 0.1) == (False, "spoke too recently")
    assert g.decide({"call": "back off", "confidence": 1.0, "urgent": True}, 2, 0.1) == (True, "ok")


def test_local_review_and_labels(tmp_path):
    pset = load_protocols(MECH_PROTOCOLS)
    m = Match.create(tmp_path, "t")
    for t, ids, call in [(3, ["surrounded"], "back off"), (6, ["surrounded"], "none"),
                         (60, ["surrounded", "right-flank"], "back off"), (90, ["late-to-extract"], "extract now")]:
        m.append("observations", {"t": t, "fired": ids, "call": call, "event": "none"})
        m.append("firings", {"t": t, "protocol": ids[0], "spoken": True, "frame": "x.jpg", "facts": {},
                             "label": None, "note": ""})
    mem = Memory(tmp_path)
    d = local_debrief(m, pset, mem)
    cats = [x["category"] for x in d["mistakes"]]
    assert cats == ["got surrounded", "got surrounded", "late to extract"]  # 3 and 6 s are one moment
    assert d["top3"][0].startswith("Keep one side clear")
    assert mem.top_habits()[0] == ("got surrounded", 2)
    answers = iter(["y", "n", "too early", "s", "q"])
    done = label_firings(m, ask=lambda _: next(answers))
    rows = m.read("firings")
    assert done == {"right": 1, "wrong": 1}
    assert [r["label"] for r in rows] == ["right", "wrong", None, None] and rows[1]["note"] == "too early"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_end_to_end_no_api_key(tmp_path, monkeypatch):
    """Recording in, review page out, with only protocols: no key, no model."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    video = tmp_path / "run.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-loop", "1", "-i", str(HUD), "-t", "12",
                    "-r", "5", "-pix_fmt", "yuv420p", str(video)], check=True)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "wtmate.toml").write_text(
        f'game = "{(ROOT / "profiles" / "mech_havoc.toml").as_posix()}"\n'
        f'protocols = "{MECH_PROTOCOLS.as_posix()}"\n[ingest]\nframe_every_s = 1.0\n')
    from wtmate.cli import main

    main(["--no-open", "review", str(video), "--label", "free"])
    match = next((tmp_path / "matches" / "mech_havoc").glob("*free*"))
    obs = [json.loads(x) for x in (match / "observations.jsonl").read_text().splitlines()]
    assert obs[0]["call"] == "watch your flank"
    assert (match / "debrief.json").exists() and (match / "review.html").exists()
    assert json.loads((match / "debrief.json").read_text())["_model"] == "local protocols"
    firings = (match / "firings.jsonl").read_text().splitlines()
    assert firings and (match / json.loads(firings[0])["frame"]).exists()
    main(["--no-open", "brief", "latest"])
    brief = (match / "brief.md").read_text()
    assert "right-flank" in brief and "[[protocol]]" in brief


class _FakeKev:
    """Stands in for a local vision model served by Ollama or LM Studio."""

    def __init__(self, data=None, fail=False):
        self.data, self.fail = data or {}, fail

    def complete_json(self, system, parts, schema):
        from wtmate.models import Result

        if self.fail:
            raise TimeoutError("model too slow")
        assert set(schema["required"]) >= {"situation", "threat_side", "heavy_enemy"}
        return Result(dict(self.data), 0.4, "fake-kev")


def test_vision_model_adds_facts_but_hud_wins():
    pset = load_protocols(MECH_PROTOCOLS)
    kev = _FakeKev({"situation": "fighting", "alive": True, "enemies_on_screen": 6, "threat_side": "Left",
                    "heavy_enemy": True, "player_moving": True, "in_menu": False, "threat": "big walker",
                    "enemies_total": 99})
    o = LocalDrill(MECH, pset, kev).observe(0.0, HUD.read_bytes())
    assert o["facts"]["enemies_total"] == 1  # the minimap reader wins over the model
    assert o["facts"]["threat_side"] == "left"
    assert {"heavy-enemy", "vision-left-flank", "right-flank"} <= set(o["fired"])
    o = LocalDrill(MECH, pset, _FakeKev(fail=True)).observe(0.0, HUD.read_bytes())
    assert o["call"] == "watch your flank"  # a broken model never stops the rules


def test_live_with_protocols(tmp_path):
    from wtmate.config import Config
    from wtmate.live import run_live

    cfg = Config(matches_dir=str(tmp_path))
    cfg.live.record_video = False
    cfg.live.frame_every_s = 0.05
    cfg.voice.enabled = False
    drill = LocalDrill(MECH, load_protocols(MECH_PROTOCOLS))
    m = run_live(cfg, drill, Memory(tmp_path), MECH, frame_source=HUD.read_bytes, max_duration_s=0.4)
    spoken = m.read("calls")
    assert spoken and spoken[0]["call"] == "watch your flank"
    assert m.read("firings")
