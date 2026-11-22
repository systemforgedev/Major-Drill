"""Optional live mode: Drill watches the screen and speaks short calls.

Screen-only: it takes screenshots, optionally reads the game's own local map
feed (your position and kill feed only), and talks. It never sends input and
never reads game memory. Everything is recorded so Major can review after.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .config import Config
from .drill import observe
from .match import Match
from .memory import Memory
from .models import Provider
from .telemetry import Telemetry, classify_feed
from .voice import Voice


class CallGate:
    """Decides whether a Drill call is worth saying out loud.

    The two live problems are lag and noise. Lag: drop advice that arrives too
    late to matter. Noise: low confidence, too soon after the last call, or a
    repeat of a recent call all get dropped.
    """

    def __init__(self, min_gap_s=6.0, repeat_gap_s=20.0, min_confidence=0.6, max_latency_s=3.0):
        self.min_gap_s, self.repeat_gap_s = min_gap_s, repeat_gap_s
        self.min_confidence, self.max_latency_s = min_confidence, max_latency_s
        self.last_any = -1e9
        self.last_by_call: dict[str, float] = {}

    def decide(self, obs: dict, now: float, latency_s: float) -> tuple[bool, str]:
        call = obs.get("call", "none")
        if call == "none":
            return False, "no call"
        if not obs.get("alive", True):
            return False, "player is dead"
        if latency_s > self.max_latency_s:
            return False, f"too late ({latency_s:.1f}s)"
        if obs.get("confidence", 0) < self.min_confidence:
            return False, "low confidence"
        if now - self.last_any < self.min_gap_s:
            return False, "spoke too recently"
        if now - self.last_by_call.get(call, -1e9) < self.repeat_gap_s:
            return False, "repeat"
        self.last_any = now
        self.last_by_call[call] = now
        return True, "ok"


def run_live(cfg: Config, drill: Provider, memory: Memory, profile, frame_source=None,
             max_duration_s: float | None = None, stop_event: threading.Event | None = None) -> Match:
    """Run one match. frame_source() -> jpeg bytes; defaults to the screen."""
    stop_event = stop_event or threading.Event()
    # The local map feed is War Thunder only; other games run screen-only.
    tel = Telemetry(cfg.telemetry.url) if cfg.telemetry.enabled and profile.key == "war_thunder" else None
    if tel and not tel.available():
        print("[live] game map feed not found at", cfg.telemetry.url, "- continuing with screen only")
        tel = None

    if tel:
        print("[live] waiting for a match to start (Ctrl+C to quit)...")
        while not tel.in_match() and not stop_event.is_set():
            time.sleep(1)

    if frame_source is None:
        from .capture import FrameGrabber

        frame_source = FrameGrabber(cfg.live.monitor, cfg.ingest.max_width).grab_jpeg

    match = Match.create(cfg.matches_dir, "live")
    if tel:
        tel.save_map(match.root / "map.png")
        tel.new_feed()  # skip kill-feed lines from before this match
    recorder = None
    if cfg.live.record_video and frame_source is not None and cfg.live.record_video:
        try:
            from .capture import Recorder

            recorder = Recorder(cfg.ffmpeg, match.video, cfg.live.video_fps)
            recorder.start()
        except Exception as e:
            print("[live] recording disabled:", e)
            recorder = None

    voice = Voice(cfg.voice.enabled, cfg.voice.rate)
    gate = CallGate(cfg.live.min_gap_s, cfg.live.repeat_gap_s, cfg.live.min_confidence, cfg.live.max_latency_s)
    t0 = time.monotonic()
    clock = lambda: round(time.monotonic() - t0, 1)  # noqa: E731
    pool = ThreadPoolExecutor(max_workers=1)
    busy = threading.Event()
    latencies: list[float] = []
    print(f"[live] recording match {match.id}")

    def poll_telemetry():
        missing_since, was_alive, out_of_match_since = None, False, None
        period = 1.0 / max(0.5, cfg.telemetry.poll_hz)
        while not stop_event.is_set():
            t = clock()
            p = tel.player()
            if p:
                match.append("track", {"t": t, **p})
                missing_since, was_alive = None, True
            elif was_alive:
                missing_since = missing_since or t
                if t - missing_since > 3:  # player icon gone: dead or spectating
                    match.append("events", {"t": missing_since, "type": "death", "msg": "player left the map"})
                    was_alive = False
            for d in tel.new_feed():
                kind = classify_feed(d.get("msg", ""), cfg.player_name)
                match.append("events", {"t": t, "type": kind or "feed", "msg": d.get("msg", "")})
            if not tel.in_match():
                out_of_match_since = out_of_match_since or t
                if t - out_of_match_since > 5:
                    stop_event.set()
            else:
                out_of_match_since = None
            time.sleep(period)

    def ask_drill(t_capture: float, jpeg: bytes):
        try:
            obs, res = observe(drill, memory, [(t_capture, jpeg)], profile)
            if not obs:
                return
            o = obs[0]
            lag = clock() - t_capture
            latencies.append(lag)
            say, why = gate.decide(o, clock(), lag)
            o |= {"latency_s": round(lag, 2), "spoken": say, "gate": why}
            match.append("observations", o)
            if say:
                voice.say(o["call"])
                match.append("calls", {"t": t_capture, "call": o["call"], "reason": o.get("reason", ""),
                                       "latency_s": round(lag, 2)})
        except Exception as e:
            print("[live] drill error:", e)
        finally:
            busy.clear()

    tel_thread = threading.Thread(target=poll_telemetry, daemon=True) if tel else None
    if tel_thread:
        tel_thread.start()
    last_saved = -1e9
    try:
        while not stop_event.is_set():
            t = clock()
            if max_duration_s and t >= max_duration_s:
                break
            jpeg = frame_source()
            if t - last_saved >= cfg.live.save_frame_every_s:
                match.frame_path(t).write_bytes(jpeg)
                last_saved = t
            if not busy.is_set():  # never queue frames: a stale frame is worse than none
                busy.set()
                pool.submit(ask_drill, t, jpeg)
            time.sleep(max(0.0, cfg.live.frame_every_s - (clock() - t)))
    except KeyboardInterrupt:
        print("\n[live] stopped by you")
    finally:
        stop_event.set()
        pool.shutdown(wait=True)
        if recorder:
            recorder.stop()
        voice.close()
        if tel_thread:
            tel_thread.join(timeout=3)
    from .drill import latency_stats

    match.write_meta({"source": "live", "duration_s": clock(), "drill_stats": latency_stats(latencies),
                      "has_video": match.video.exists()})
    print(f"[live] match saved to {match.root}")
    return match
