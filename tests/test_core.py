import json
import shutil
import subprocess
from pathlib import Path

import pytest

from wtmate.bench import expected_calls, score
from wtmate.config import load_config
from wtmate.live import CallGate
from wtmate.memory import Memory
from wtmate.models import Image, MockProvider, Text, _frame_times
from wtmate.schema import OBSERVATION_SCHEMA
from wtmate.stats import dedupe_times, parse_grid
from wtmate.telemetry import classify_feed, find_player


def test_parse_grid_letters_are_rows():
    assert parse_grid("D4") == (3, 3)
    assert parse_grid("b-10") == (9, 1)
    assert parse_grid("") is None and parse_grid("??") is None


def test_dedupe_times():
    assert dedupe_times([10, 12, 40, 41, 90], 20) == [10, 40, 90]


def test_gate_blocks_noise_and_lag():
    g = CallGate(min_gap_s=6, repeat_gap_s=20, min_confidence=0.6, max_latency_s=3)
    o = {"call": "pull back", "confidence": 0.9, "alive": True}
    assert g.decide({"call": "none"}, 0, 0.5) == (False, "no call")
    assert g.decide(o, 0, 4.0)[1].startswith("too late")
    assert g.decide(o | {"confidence": 0.3}, 0, 1) == (False, "low confidence")
    assert g.decide(o | {"alive": False}, 0, 1) == (False, "player is dead")
    assert g.decide(o, 10, 1) == (True, "ok")
    assert g.decide({"call": "hold position", "confidence": 0.9}, 12, 1) == (False, "spoke too recently")
    assert g.decide(o, 20, 1) == (False, "repeat")
    assert g.decide(o, 31, 1) == (True, "ok")


def test_feed_classification():
    assert classify_feed("Ivan (T-34) destroyed Bob (Tiger)", "ivan") == "kill"
    assert classify_feed("Bob (Tiger) destroyed Ivan (T-34)", "Ivan") == "death"
    assert classify_feed("Bob (Tiger) destroyed Joe (T-34)", "Ivan") is None
    assert classify_feed("anything", "") is None


def test_find_player():
    objs = [{"icon": "MediumTank", "x": 0.1, "y": 0.1}, {"icon": "Player", "x": 0.5, "y": 0.25, "dx": 1, "dy": 0}]
    assert find_player(objs) == {"x": 0.5, "y": 0.25, "dx": 1.0, "dy": 0.0}


def test_mock_reads_frame_labels():
    parts = [Text("frame t=3.0s"), Image(b"x"), Text("frame t=6.0s"), Image(b"y"), Text("go")]
    assert _frame_times(parts) == [3.0, 6.0]
    res = MockProvider().complete_json("s", parts, OBSERVATION_SCHEMA)
    assert [o["t"] for o in res.data["observations"]] == [3.0, 6.0]


def test_memory_counts_once_and_merges_lessons(tmp_path):
    m = Memory(tmp_path)
    d = {"mistakes": [{"category": "pushed alone"}], "top3": [], "lessons_updates": ["Rule A", "rule b"]}
    m.record_debrief("m1", d)
    m.record_debrief("m1", d)  # re-run must not double count
    m.record_debrief("m2", {"mistakes": [{"category": "pushed alone"}], "lessons_updates": ["rule a", "Rule C"]})
    m2 = Memory(tmp_path)
    assert m2.top_habits() == [("pushed alone", 2)]
    assert m2.lessons == ["rule a", "Rule C", "rule b"]


def test_score_uses_major_as_answer_key():
    debrief = {"call_grades": [{"t": 30, "call": "pull back", "grade": "right", "should_have_said": ""},
                               {"t": 60, "call": "push now", "grade": "wrong", "should_have_said": "hold position"}]}
    assert expected_calls(debrief) == [(30, "pull back"), (60, "hold position")]
    cand = [{"t": 27, "call": "pull back", "confidence": 0.9, "event": "none", "minimap_grid": "C3"},
            {"t": 60, "call": "push now", "confidence": 0.9, "event": "death", "minimap_grid": "C4"}]
    ref = [{"t": 27, "minimap_grid": "C3", "event": "none"}, {"t": 60, "minimap_grid": "C3", "event": "death"}]
    s = score(cand, ref, debrief, duration_s=120)
    assert s["call_accuracy"] == 0.5 and s["death_recall"] == 1.0 and s["grid_match"] == 0.5
    assert s["calls_per_min"] == 1.0


def test_config_rejects_typos(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('[fast]\nmodle = "x"\n')
    with pytest.raises(ValueError):
        load_config(p)
    p.write_text('player_name = "Ivan"\n[fast]\nprovider = "mock"\n[[contenders]]\nname = "qwen"\nprovider = "mock"\nmodel = "q"\n')
    c = load_config(p)
    assert c.player_name == "Ivan" and c.fast.provider == "mock" and c.contenders[0]["name"] == "qwen"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_end_to_end_mock(tmp_path, monkeypatch):
    """Recording in, review page out, then a plan and a bench, all with fake models."""
    video = tmp_path / "clip.mkv"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=10",
                    "-t", "45", str(video)], check=True)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "wtmate.toml").write_text(
        'matches_dir = "m"\n[ingest]\nframe_every_s = 3.0\n[[contenders]]\nname = "rival"\nprovider = "mock"\nmodel = "r"\n')
    from wtmate.cli import main

    main(["--mock", "--no-open", "review", str(video), "--label", "test"])
    match = next(p for p in (tmp_path / "m").iterdir() if p.is_dir() and p.name != "_profile")
    assert len(list((match / "frames").glob("*.jpg"))) == 15
    assert (match / "video.mp4").exists() and (match / "debrief.json").exists()
    html = (match / "review.html").read_text()
    assert "__DATA__" not in html and '"top3"' in html
    assert (tmp_path / "m" / "index.html").exists()
    main(["--mock", "--no-open", "plan"])
    assert json.loads((tmp_path / "m" / "_profile" / "plan.json").read_text())["drill_lessons"]
    main(["--mock", "--no-open", "bench", "latest", "--limit", "6"])
    scores = json.loads((match / "bench" / "scores.json").read_text())
    assert set(scores) == {"drill (claude-haiku-5-5)", "rival"}
    assert "__SCORES__" not in (match / "bench" / "compare.html").read_text()
