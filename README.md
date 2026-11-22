# wtmate: an AI teammate for any game (War Thunder first)

Record a match, hand it over, and get back a timeline of what happened, a heatmap of where you
spent time and died, and a short after-action report (AAR) on why you lost and what to fix next.

Two roles do the work:

- **Drill** is the fast one. It reads frames and picks short calls: check minimap, flank, pull back, hold.
- **Major** is the slow, careful one. It reviews the whole match, tests several explanations for
  each death, writes the AAR, grades Drill's calls, and keeps Drill's lessons-learned file up to date.

**By default it's free and local: no API key, no cloud.** Drill follows **protocols**, plain
if-then rules like "enemies on your right flank, priority 1, say *watch your right*", and reads the
screen with simple HUD checks (minimap dots, bars, colours, optional OCR for numbers). Major writes
the review from what the protocols saw. Better protocols come from reviewing your runs in a Claude
chat. See [PROTOCOLS.md](PROTOCOLS.md) and [SETUP_WINDOWS.md](SETUP_WINDOWS.md).

Both roles are also plug-in slots. Put Claude, a local open model (Qwen, Keye, anything served by Ollama,
LM Studio, llama.cpp or vLLM) or your own bot behind either one.

## Games

Everything game-specific lives in a **game profile**: how to read the screen, what Drill may say,
and which mistakes Major tags. Built in: `war_thunder` and `generic_action`. Your own game is a
TOML file, for example [`profiles/mech_havoc.toml`](profiles/mech_havoc.toml) (a draft).

```
wtmate --game profiles/mech_havoc.toml review my_run.mp4
```

Each game keeps its own matches, habits and lessons under `matches/<game>/`.

Roadmap: prove it on a single-player game (Mech Havoc), then multiplayer, then War Thunder with
real data, then a pitch to Gaijin.

## Tiers

| Tier | What you get | What you need |
| --- | --- | --- |
| **Base (everyone)** | Upload any recording. Timeline, heatmap, AAR, career page, Major's improvement plan. | Any PC. Cloud models, or a local model if you don't mind waiting a few minutes after the match. |
| **Live (optional)** | Drill watches your screen and talks during the match. | A cloud model with good internet, or a GPU with room for the game *and* a small vision model. |

The base tier is the product. Live mode is built and tested against a fake game server, but it
needs real-world tuning (see [PROBLEMS.md](PROBLEMS.md)).

## Rules and privacy

- **Screen only.** wtmate never sends input to the game and never reads game memory.
- Live mode can read the game's own local map page (`127.0.0.1:8111`), which only shows what your
  minimap and kill feed show. It logs your own position and the kill feed, never enemy positions.
- Gaijin's 2026 terms say game content may not be used for AI training or model building without
  their written permission. wtmate sends frames to a model to *advise you*; it does not train
  models. Keep it that way: don't pool other players' footage into a training set without
  Gaijin's OK.
- Recordings stay on your PC in `matches/`. Frames go to whichever model provider you configure.

## Install (Windows, macOS or Linux)

1. Python 3.11+ and [ffmpeg](https://ffmpeg.org/download.html) on your PATH.
2. In this folder:
   ```
   python -m venv .venv
   .venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
   pip install -e .                # add [live] for live mode: pip install -e ".[live]"
   copy wtmate.example.toml wtmate.toml   # macOS/Linux: cp
   ```
3. Optional, later: for Claude models, `pip install -e ".[cloud]"` and set `ANTHROPIC_API_KEY`.
4. `wtmate check` tells you what's missing.

## Use

```
wtmate review my_match.mp4           # Drill (protocols) reads it, Major writes the review. Free.
wtmate protocols test shot.png       # what the HUD readers see on a screenshot, and what Drill would say
wtmate protocols check               # validate the protocol file
wtmate label latest                  # mark each call right or wrong (training data for later)
wtmate brief latest                  # brief.md to paste into a Claude chat for better protocols
wtmate --mock review my_match.mp4    # test the model path with fake models
wtmate plan                          # model mode only: Major's plan, rewrites Drill's lessons
wtmate bench latest --limit 40       # face-off: several Drill models on the same footage
wtmate live                          # optional: live calls during a match
wtmate pages                         # rebuild all pages
```

Pages open in your browser: `matches/<game>/<match>/review.html` (one match) and `matches/<game>/index.html` (career).

Any recording works: ShadowPlay, OBS, Xbox Game Bar, or a capture of a server replay. Longer
recordings cost more; one frame every 3 seconds is the default (`[ingest] frame_every_s`).

### Rough cost per 15-minute match (cloud defaults)

About 300 frames. Drill (Claude Haiku 5.5, batched 8 frames per request) is cheap; Major
(Claude Opus 5.5) reads Drill's log plus 24 key frames. A rough estimate from list prices is
around $0.30 per match. Run `wtmate review` once and check your usage page for the real number.

## Local models

Any server that speaks the OpenAI-style `/chat/completions` API with image input works. Set
`provider = "openai_compat"`, `base_url` and `model` in `wtmate.toml`. Sizes to plan around
(4-bit quantized, from [this guide](https://codersera.com/blog/qwen3-vl-4b-vs-qwen3-vl-8b-benchmarks-vram-guide/)):

| Model | File size | Fits | Good for |
| --- | --- | --- | --- |
| Qwen3-VL 2B | ~1.9 GB | 4 GB GPUs | Live Drill next to the game on modest cards |
| Qwen3-VL 4B | ~3.3 GB | 6-8 GB VRAM | Best first try for live Drill |
| Qwen3-VL 8B | ~6.1 GB | 12-16 GB VRAM | Better reads; Drill on big cards, or Major locally |
| [Keye-VL 8B](https://huggingface.co/Kwai-Keye/Keye-VL-8B-Preview) | ~12 GB at 8-bit | 16 GB+ | Video-focused; Major locally, or Drill on a 24-32 GB card |

War Thunder itself needs several GB of VRAM, so for live Drill on one GPU start with the 4B and
measure with `wtmate bench --batch 1`.

## Layout

```
wtmate/
  protocols.py  protocol files: conditions, priorities, the rules engine
  hud.py        HUD readers: bars, colours, minimap dots, OCR (no AI)
  local.py      free Drill: HUD + protocols (+ optional local vision model), firing log, labels
  local_major.py free Major: review from protocol firings
  drill.py      model Drill: frame reads and calls (offline batches, live single frames)
  major.py      Major: AAR per match, improvement plan across matches
  models.py     provider slots: anthropic, openai_compat, mock
  profiles.py   game profiles (built-ins + loader for your own .toml)
  ingest.py     recording -> match folder + sampled frames (ffmpeg)
  memory.py     habit counts + Drill's lessons-learned file
  stats.py      numbers for the pages (deaths, kills, heatmap, time split)
  review.py     builds review.html and index.html from assets/
  bench.py      model face-off + scores
  live.py       live loop, call gate (lag and noise filter)
  telemetry.py  the game's own local map page (live mode only)
  capture.py    screenshots + screen recording (live mode only)
  voice.py      text to speech (live mode only)
profiles/                 extra game profiles (Mech Havoc)
protocols/                protocol files per game (Mech Havoc starter set)
tools/fake_wt_server.py   pretend War Thunder map server for testing live mode
tests/                    `pytest -q`
```

License: MIT.
