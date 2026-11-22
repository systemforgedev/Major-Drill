"""Model providers behind one small interface, so the fast tier can be swapped.

Every provider takes a system prompt, a list of parts (text and JPEG images)
and a JSON schema, and returns the parsed JSON plus timing info.
"""
from __future__ import annotations

import base64
import json
import os
import random
import time
import urllib.request
from dataclasses import dataclass

from .config import ModelCfg


@dataclass
class Text:
    text: str


@dataclass
class Image:
    jpeg: bytes


@dataclass
class Result:
    data: dict
    latency_s: float
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class ModelError(RuntimeError):
    pass


class Provider:
    def complete_json(self, system: str, parts: list, schema: dict) -> Result:
        raise NotImplementedError


# Models that accept the server-side refusal fallback parameter.
_FALLBACK_MODELS = {"claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}


class AnthropicProvider(Provider):
    def __init__(self, cfg: ModelCfg):
        import anthropic  # imported here so mock runs need no SDK

        self.cfg = cfg
        self.client = anthropic.Anthropic()

    def _content(self, parts):
        out = []
        for p in parts:
            if isinstance(p, Image):
                out.append({"type": "image", "source": {
                    "type": "base64", "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(p.jpeg).decode("ascii")}})
            else:
                out.append({"type": "text", "text": p.text})
        return out

    def complete_json(self, system, parts, schema):
        kwargs = dict(
            model=self.cfg.model,
            max_tokens=self.cfg.max_tokens,
            # Stable system prompt first, cached; frames change every call.
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": self.cfg.effort,
                           "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": self._content(parts)}],
        )
        start = time.perf_counter()
        if self.cfg.model in _FALLBACK_MODELS:
            # If a safety classifier declines, the API retries on a fallback model.
            with self.client.beta.messages.stream(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
            ) as stream:
                msg = stream.get_final_message()
        else:
            with self.client.messages.stream(**kwargs) as stream:
                msg = stream.get_final_message()
        latency = time.perf_counter() - start
        if msg.stop_reason == "refusal":
            raise ModelError(f"Model declined: {getattr(msg.stop_details, 'category', None)}")
        if msg.stop_reason == "max_tokens":
            raise ModelError("Response hit max_tokens; raise max_tokens in the config.")
        text = next((b.text for b in msg.content if b.type == "text"), None)
        if text is None:
            raise ModelError("No text block in response.")
        return Result(json.loads(text), latency, msg.model,
                      msg.usage.input_tokens, msg.usage.output_tokens)


class OpenAICompatProvider(Provider):
    """Any server that speaks the OpenAI-style /chat/completions API.

    Use this for a local or third-party fast model (for example one served by
    llama.cpp, vLLM, LM Studio or Ollama). Set base_url and model in the config.
    """

    def __init__(self, cfg: ModelCfg):
        if not cfg.base_url:
            raise ValueError("openai_compat provider needs base_url in the config")
        self.cfg = cfg

    def complete_json(self, system, parts, schema):
        content = []
        for p in parts:
            if isinstance(p, Image):
                b64 = base64.standard_b64encode(p.jpeg).decode("ascii")
                content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
            else:
                content.append({"type": "text", "text": p.text})
        body = {
            "model": self.cfg.model,
            "max_tokens": self.cfg.max_tokens,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": content}],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "output", "schema": schema}},
        }
        headers = {"Content-Type": "application/json"}
        if self.cfg.api_key_env and os.environ.get(self.cfg.api_key_env):
            headers["Authorization"] = f"Bearer {os.environ[self.cfg.api_key_env]}"
        req = urllib.request.Request(self.cfg.base_url.rstrip("/") + "/chat/completions",
                                     data=json.dumps(body).encode(), headers=headers)
        start = time.perf_counter()
        with urllib.request.urlopen(req, timeout=60) as resp:
            out = json.loads(resp.read())
        latency = time.perf_counter() - start
        text = out["choices"][0]["message"]["content"]
        usage = out.get("usage", {})
        return Result(json.loads(text), latency, self.cfg.model,
                      usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))


class MockProvider(Provider):
    """Deterministic fake model for tests and dry runs. Costs nothing."""

    def __init__(self, cfg: ModelCfg | None = None, seed: int = 7):
        self.rng = random.Random(seed)

    def complete_json(self, system, parts, schema):
        props = schema.get("properties", {})
        if "observations" in props:
            item = props["observations"]["items"]["properties"]
            data = {"observations": [self._obs(t, item) for t in _frame_times(parts)]}
        elif "top3" in props:
            data = self._debrief(props["mistakes"]["items"]["properties"]["category"]["enum"])
        elif "drill_lessons" in props:
            data = {"headline": "Mock plan: you die to flanks after holding one spot too long.",
                    "death_patterns": [{"where": "D4", "why": "Flanked from the left while static", "matches_seen": 2}],
                    "focus_areas": [{"goal": "Check the minimap every 10 seconds", "why": "Most deaths came from the side",
                                     "practice": "Say 'map' out loud each time you check, for 3 matches",
                                     "measure": "'ignored minimap threat' count per match"}],
                    "progress": "Too little data yet.",
                    "drill_lessons": ["If red markers appear on a flank of the minimap, call check minimap.",
                                      "If the player fired twice from one spot, call change position."]}
        else:
            raise ValueError("MockProvider does not know this schema")
        return Result(data, 0.05, "mock")

    def _obs(self, t, item):
        r = self.rng
        calls, sits, events = item["call"]["enum"], item["situation"]["enum"], item["event"]["enum"]
        dead = r.random() < 0.06
        col, row = "ABCDEFGH"[int(t / 40) % 8], 1 + int(t / 25) % 8
        call = "none" if r.random() < 0.6 else r.choice(calls[1:])
        return {
            "t": t, "alive": not dead,
            "situation": r.choice(sits),
            "minimap_grid": "" if dead else f"{col}{row}",
            "threat": "" if r.random() < 0.5 else "enemy tank on the left ridge",
            "event": "death" if dead else (events[2] if r.random() < 0.05 else "none"),
            "hypotheses": [{"guess": "enemy flanking left", "likelihood": 0.6},
                           {"guess": "enemy holding the ridge", "likelihood": 0.3}],
            "call": call, "confidence": round(r.uniform(0.4, 0.95), 2),
            "reason": "red marker near left flank",
        }

    def _debrief(self, cats):
        return {
            "summary": "Mock debrief. You spent long stretches in one spot and died twice to flanks.",
            "mistakes": [{
                "t": 120.0, "category": cats[0],
                "what_happened": "Two enemies showed on the left of the minimap and you stayed put.",
                "better_option": "Check the minimap every 10 seconds and pull back behind cover.",
                "hypotheses_checked": [
                    {"hypothesis": "Out-gunned head on", "verdict": "rejected", "evidence": "Shot came from the side."},
                    {"hypothesis": "Flanked unseen", "verdict": "supported", "evidence": "Minimap showed red on the left 15 s earlier."}],
            }, {
                "t": 300.0, "category": cats[min(2, len(cats) - 1)],
                "what_happened": "Held the same bush for 90 seconds after firing.",
                "better_option": "Move after two shots.", "hypotheses_checked": [],
            }],
            "top3": ["Glance at the minimap every 10 seconds.", "Relocate after two shots.", "Don't push alone."],
            "good_plays": ["Good first shot placement on the opening engagement."],
            "call_grades": [{"t": 105.0, "call": "check minimap", "grade": "right", "should_have_said": ""}],
            "lessons_updates": ["If you fired twice from one spot, call change position."],
        }


def _frame_times(parts):
    """Frames are always preceded by a label part 'frame t=12.0s'."""
    times = []
    for i, p in enumerate(parts):
        if isinstance(p, Image) and i > 0 and isinstance(parts[i - 1], Text):
            label = parts[i - 1].text
            if "t=" in label:
                times.append(float(label.split("t=")[1].split("s")[0]))
    return times


def make_provider(cfg: ModelCfg) -> Provider:
    if cfg.provider == "anthropic":
        return AnthropicProvider(cfg)
    if cfg.provider == "openai_compat":
        return OpenAICompatProvider(cfg)
    if cfg.provider == "mock":
        return MockProvider(cfg)
    raise ValueError(f"Unknown provider {cfg.provider!r}")
