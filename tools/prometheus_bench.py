"""Run Project Prometheus's local vision models on the same Mech Havoc frames.

Each model is started the way Prometheus starts it (tools/assistant_arena/run.py):
the Unsloth llama.cpp build, every layer on the GPU, thinking switched off. One
model at a time, so both fit on one card. No API key, nothing leaves the PC.

For every frame each model answers twice:
  drill  - Drill's real prompt and JSON schema (what live mode would say)
  coach  - a plain question with the profile's screen guide: what should the player do right now?

Usage:
  python tools/prometheus_bench.py bench/prometheus-2026-11-23
The folder must hold frames/*.jpg and frames.json ([{"file", "t", "note"}]).
Writes <folder>/runs/<model><tag>.json. Inkling has no "thinking off" switch
(reasoning_effort=none is its minimum), so --think-budget caps it instead.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wtmate.drill import _parts_for, system_prompt  # noqa: E402
from wtmate.memory import Memory  # noqa: E402
from wtmate.models import Image  # noqa: E402
from wtmate.profiles import load_profile  # noqa: E402
from wtmate.schema import observation_schema  # noqa: E402

PROMETHEUS = Path(os.environ.get("PROMETHEUS_DIR", r"C:\Users\ivant\Documents\ChatGPT\Prometheus"))
# Same switches Prometheus's Assistant Arena uses to turn thinking off.
TEMPLATE = {"qwen": {"enable_thinking": False}, "inkling": {"reasoning_effort": "none"}}

COACH = """You are an experienced Mech Havoc player coaching a friend who is playing right now.
How to read the screen:
{screen_guide}

Look at this screenshot. In 2 or 3 short sentences: what is happening, and the single most useful
thing the player should do in the next 10 seconds. Only use what you can actually see."""


def manifest(key: str) -> dict:
    return json.loads((PROMETHEUS / "models" / f"dialogue-{key}-manifest.json").read_text(encoding="utf-8"))


def start(key: str, log: Path):
    spec, ink, qwen = manifest(key), manifest("inkling"), manifest("qwen")
    exe = Path(ink["executable"])  # Unsloth build runs both models
    env = {**os.environ, "PATH": str(Path(qwen["executable"]).parent) + os.pathsep + os.environ["PATH"]}
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    cmd = [str(exe), "--model", spec["path"], "--mmproj", spec["vision"]["path"], "--host", "127.0.0.1",
           "--port", str(port), "--ctx-size", "16384", "--n-gpu-layers", "999", "--device", "CUDA0",
           "--flash-attn", "on", "--parallel", "1", "--no-ui", "--offline"]
    proc = subprocess.Popen(cmd, cwd=exe.parent, env=env, stdout=log.open("wb"), stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    base, t0 = f"http://127.0.0.1:{port}", time.perf_counter()
    while time.perf_counter() - t0 < 300:
        if proc.poll() is not None:
            raise RuntimeError(f"llama-server exited ({proc.returncode}); see {log}")
        try:
            with urllib.request.urlopen(base + "/health", timeout=1) as r:
                if r.status == 200:
                    return proc, base, round(time.perf_counter() - t0, 1)
        except Exception:
            pass
        time.sleep(0.5)
    proc.kill()
    raise TimeoutError("llama-server did not become healthy")


def chat(base: str, key: str, system: str | None, content: list, schema: dict | None, max_tokens: int,
         think_budget: int | None = None):
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": content}]
    body = {"messages": msgs, "max_tokens": max_tokens, "temperature": 0.2, "seed": 7,
            "chat_template_kwargs": TEMPLATE[key]}
    if think_budget is not None:  # llama.cpp per-request cap on thinking tokens
        body["reasoning_budget_tokens"] = think_budget
    if schema:
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": "output", "schema": schema}}
    req = urllib.request.Request(base + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as r:
        out = json.loads(r.read())
    msg = out["choices"][0]["message"]
    usage = dict(out.get("usage", {}), reasoning_chars=len(msg.get("reasoning_content") or ""))
    return (msg.get("content") or "").strip(), round(time.perf_counter() - t0, 2), usage


def image_part(jpeg: bytes) -> dict:
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()}}


def to_openai(parts) -> list:
    return [image_part(p.jpeg) if isinstance(p, Image) else {"type": "text", "text": p.text} for p in parts]


def run(folder: Path, keys: list[str], think_budget: int | None = None, tag: str = ""):
    frames = json.loads((folder / "frames.json").read_text(encoding="utf-8"))
    profile = load_profile(str(ROOT / "profiles" / "mech_havoc.toml"))
    system = system_prompt(Memory(folder / "_memory"), profile)
    schema = observation_schema(profile)
    (folder / "runs").mkdir(exist_ok=True)
    for key in keys:
        log = folder / "runs" / f"{key}-server.log"
        proc, base, load_s = start(key, log)
        print(f"[{key}] up in {load_s}s", flush=True)
        rows = []
        try:
            chat(base, key, None, [{"type": "text", "text": "Say ok."}], None, 8)  # warm-up
            for f in frames:
                jpeg = (folder / "frames" / f["file"]).read_bytes()
                text, lat, use = chat(base, key, system, to_openai(_parts_for([(f["t"], jpeg)])), schema, 3000, think_budget)
                try:
                    drill = json.loads(text)["observations"][0]
                except Exception as e:  # keep the raw answer; a broken answer is a result too
                    drill = {"parse_error": str(e), "raw": text[:2000]}
                coach, lat2, use2 = chat(base, key, None, [{"type": "text", "text": COACH.format(screen_guide=profile.screen_guide)}, image_part(jpeg)], None, 1500, think_budget)
                rows.append({"file": f["file"], "t": f["t"], "drill": drill, "drill_s": lat,
                             "coach": coach, "coach_s": lat2,
                             "tokens": {"drill": use.get("completion_tokens"), "coach": use2.get("completion_tokens"),
                                        "drill_thinking_chars": use["reasoning_chars"],
                                        "coach_thinking_chars": use2["reasoning_chars"]}})
                print(f"[{key}] {f['file']}: {drill.get('call')} | {lat}s / {lat2}s", flush=True)
        finally:
            proc.terminate()
            try:
                proc.wait(20)
            except subprocess.TimeoutExpired:
                proc.kill()
        spec = manifest(key)
        (folder / "runs" / f"{key}{tag}.json").write_text(json.dumps(
            {"model": spec["filename"], "vision": spec["vision"]["filename"], "load_s": load_s,
             "think_budget": think_budget, "frames": rows},
            indent=2), encoding="utf-8")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("models", nargs="*", default=["qwen", "inkling"])
    ap.add_argument("--think-budget", type=int, help="cap thinking tokens per answer (Inkling always thinks)")
    ap.add_argument("--tag", default="", help="suffix for the output file, e.g. -capped")
    a = ap.parse_args()
    run(a.folder, a.models, a.think_budget, a.tag)
