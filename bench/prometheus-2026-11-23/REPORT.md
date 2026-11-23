# First model face-off: Qwen vs Inkling 2 Mini on Mech Havoc (2026-11-23)

Two local vision models from Project Prometheus looked at the same 8 Mech Havoc frames.
Each answered twice per frame: once with **Drill's real prompt and JSON schema** (the call live
mode would make), and once with a plain **coach question** ("what's happening, and the single
most useful thing to do in the next 10 seconds?"). Then Claude read the same frames at full size
as the reference. No API key, nothing left the PC.

![The 8 frames](frames-sheet.jpg)

## Verdict (first run, v1)

| | Qwen 3.8 27B (Q5) | Inkling 2 Mini (Q4) | Inkling, thinking capped at 256 |
| --- | --- | --- | --- |
| Live call right (what Drill would say at its 0.6 confidence bar) | 4 / 8 | 6 / 8 | 6 / 8 |
| Top pick right or acceptable, ignoring confidence | 4 / 8 | 4 / 8 | 4 / 8 |
| Seconds per Drill frame | **3.3 to 4.7** | 10.5 to 19.7 | 8.1 to 9.0 |
| Seconds per coach answer | **1.1 to 1.5** | 9.2 to 17.3 | 5.6 to 6.3 |
| Reads HUD numbers right (HP, ammo, objectives) | poor | **good** | good |
| Invents enemies that aren't there | often | sometimes | sometimes |
| "situation" label wrong | 6 / 8 (menu or low health in a fight) | 8 / 8 ("low health" 7 times at full HP) | 7 / 8 |
| False events logged | 2 "mission complete" | 4 ("big hit taken", "objective done", "mission complete") | 3 |

**In short:** Inkling *sees* the HUD much better, and its advice reads like a real teammate's,
but it can't switch off thinking, so it is 3 to 10 times slower. Qwen is fast enough to be close
to live speed but misreads the screen a lot. Its 4/8 score mostly comes from saying "none".
Neither model is good enough to pick calls on its own. That supports the PR #2 design:
**HUD readers and protocols decide, a model only describes.**

Inkling's 6/8 needs a caveat. On the quiet frames its wrong top picks fell below Drill's 0.6
confidence bar, so Drill would have stayed silent, which happened to be right. The bar did the
work, not the model.

## Rerun after the profile fixes (v2)

The first run showed two misreads that both models shared, so the Mech Havoc profile's screen
guide got two new lines: **cyan or blue glow = friendly (allies, your own turrets), red minimap
dots = enemies**, and **single-shot weapons (Gauss Rifle, AC-20 Canister) show 1 when loaded,
only 0 is empty**. The coach question now gets the same screen guide Drill does. Same 8 frames,
same settings. Raw answers are in `runs/*-v2.json`.

| | Qwen v1 → v2 | Inkling v1 → v2 | Inkling capped v1 → v2 |
| --- | --- | --- | --- |
| Live call right (0.6 bar) | 4 → **6** / 8 | 6 → 6 / 8 | 6 → 5 / 8 |
| Top pick right or acceptable | 4 → **6** / 8 | 4 → 4 / 8 | 4 → 5 / 8 |
| Treats friendly units as enemies | yes → **no** | yes → **no** | yes → **no** |
| Says the Gauss "1" is nearly empty | 8 frames → **0** | 8 → **0** | 8 → **0** |
| Says "reload the HMG" on f5 (HMG at 0) | no → no | no → **yes** | no → **yes** |
| False events | 2 → 1 | 4 → 2 | 3 → 2 |
| "situation" label wrong | 6 → 7 / 8 | 8 → 8 / 8 | 7 → 8 / 8 |
| Sees the red minimap dots in f8 | no → no | no → no | no → no |
| Seconds per Drill frame / coach answer | 3.9-6.5 / 1.2-1.8 | 9.7-18.9 / 9.9-18.3 | 8.0-9.1 / 5.6-5.9 |

**What the fixes changed:**
- Both fixes worked in every run. Nobody tells the player to back off from allies or shoot their
  own turret any more. Inkling now says "don't fire into the cyan allies" on f4, and Qwen calls
  them "your own deployed turrets, not threats". Nobody calls the Gauss empty; Inkling even
  says "Gauss is at 1 (normal), don't reload yet".
- With the Gauss noise gone, Inkling's f5 advice now matches the reference exactly: "reload the
  empty HMG (R)". Capped Inkling found it too, but at 0.55 confidence Drill would stay quiet.
- Qwen gained the most on calls (4 → 6). Its f4 "back off" and f6 "back off at low health" are
  gone. On f8 its coach answer even says "you're just idling on the road, move forward to find
  the artillery", which is the reference advice.

**What they didn't change:**
- The "situation" and "event" labels are still wrong most of the time. Qwen still calls live
  play "menu" or "mission complete". Inkling still says "low health" or "menu" at full HP.
  These fields should come from HUD readers, not the model.
- Nobody sees the red minimap dots in f8. That's still the minimap HUD reader's job.
- They still invent threats now and then. Qwen's f6 coach answer has an "enemy walker on the left".
  Inkling's f8 answer treats a yellow ground marker as "the visible threat".

The verdict stays the same. Prompt fixes in the profile are cheap and clearly help. Qwen is now
a reasonable fast describer. Inkling gives the best advice but only fits the post-match review.

## Frame by frame (v1, before the fixes)

Reference = Claude's read. ✓ right, ~ acceptable, ✗ wrong. "(silent)" = below 0.6, Drill says nothing.

| Frame | What's really there | Best call | Qwen call | Inkling call |
| --- | --- | --- | --- | --- |
| f1 range | Practice targets at 50-60 m, full HP, all call-ins ready | none | none ✓, but labelled "mission complete" | hit the objective 0.5 (silent) ✓ |
| f2 range | HMG 26 and firing, a dozen targets bunched | call the mortar | none ~, labelled "menu screen" | focus the big one 0.55 (silent) ~ |
| f3 range | Same, with a Hephaestus aim overlay | none | none ✓, labelled "menu screen" | hit the objective 0.6 ✗ |
| f4 range | Friendly units (cyan glow) near the player | none | **back off 0.85 ✗**: friends read as enemies, full HP read as low | reload later 0.55 (silent) ✓ |
| f5 street | **HMG at 0**, nothing shooting, objectives east | reload now | none ✗ | **reload now 0.65 ✓** |
| f6 street 00:04 | Mission start, own turret deploying, no enemies | none / move to objective | back off 0.75 ✗: "HP 368 is getting low" | reload later 0.65 ✗ |
| f7 street 00:08 | Hasn't moved, nothing around | keep moving | **keep moving ✓** | hit the objective 0.6 ~ |
| f8 street 00:12 | Still hasn't moved, **red dots on the minimap east** | keep moving | none ✗, labelled "mission complete" | hit the objective 0.6 ~ |

### What each one advised (the coach answers)

| Frame | Qwen | Inkling | Claude |
| --- | --- | --- | --- |
| f2 | "Hold the doorway, use your Precision Mortar (key 1)" (it treats training dummies as a swarm) | "Use the HMG on the cluster rather than the last Gauss round, consider a call-in" | Mortar the cluster; reload HMG (26) after |
| f4 | "Taking fire from two enemies, get behind the wall, mortar them" ✗ | "Finish the targets on the right, then extract" ✗ (also shoots friends) | They're friendly. Nothing to do |
| f5 | "Get into the road and fire your Gauss to help your buddy" | "Ammo nearly empty, use a ready call-in, don't out-gun it with empty weapons" | HMG is empty and it's safe: reload now, then push east |
| f7 | "Enemy vehicle to your left, turn and fire" ✗ (nothing there) | "Stop holding the beam up, engage the contact" (good catch: the aim line points north) | You've stood still 4 s, move east to the objectives |
| f8 | "Drive forward to grab the green pickup" ✗ (it's your turret) | "Engage the green mech ahead" ✗ (it's your turret) | Enemies on the minimap east; stop idling, move up behind your turret, face east |

## What both got wrong

- **Gauss Rifle "1".** Both said the Gauss is "nearly empty" in every frame. It shows 1 in all 8
  frames, and so does the AC-20 Canister, so it is most likely a one-shot-per-reload weapon and
  1 is normal. Worth checking in a vanilla run, then saying so in the profile's screen guide.
- **Friendly vs enemy.** Neither model knows cyan glow means friendly. Qwen told the player to
  back off from its allies; Inkling told the player to shoot its own turret. Add it to the
  profile's screen guide.
- **Minimap.** Neither noticed the red dots appearing east in f8, the one real early warning.
  That is a job for the minimap HUD reader, which already counts red dots.
- **Standing still.** The real lesson in f6 to f8 is "stood still for 8 seconds at mission start".
  No single frame shows it. A protocol with `hold_s` on a "not moving" fact catches it; a model
  looking at one frame never will.
- **Labels and events.** "situation" and "event" were wrong most of the time (Inkling said "low
  health" at 360/360 HP 7 times). If these went into the post-match review they'd invent deaths,
  hits and mission ends. HP, objectives and extraction should come from HUD readers only.

## What this means for Major Drill

1. **Live Drill (seconds matter):** keep protocols + HUD readers in charge. If a model is added
   as the optional describer, Qwen is the only one near the 3-second budget, and only for short
   answers (1.1 to 1.5 s). The full Drill JSON at 3.3 to 4.7 s is over budget.
2. **Post-match review (Major):** Inkling fits. 10 to 20 s per frame is fine after a match, and its
   HUD reading and advice are clearly better. Capping its thinking at 256 tokens halves the time
   and the advice is about as good.
3. **Prompt fixes that cost nothing:** "cyan glow = friendly" and "Gauss and AC-20 show 1 when
   loaded" are now in the profile (see v2). The Gauss line is still an inference from these
   frames: check it once in a vanilla run.

## Limits of this test

- **No real recording exists on the PC.** Steam screenshots, Videos and NVIDIA folders are empty.
  These 8 frames are the best available: 4 from Hephaestus's training-range test fixtures and 4
  from its in-mission proof shots (one 3-frame, 8-second sequence). All were taken **with the
  Hephaestus mods on** (the BUDDY mech, "Suppress here" markers, a fifth call-in, the aim
  overlay in f3). I did not play the game with automated input.
- 8 frames and one reference reader (Claude). It shows the pattern, not a precise score.
- `wtmate bench` itself needs a recorded match plus a reference review, so this run used a
  small runner, [`tools/prometheus_bench.py`](../../tools/prometheus_bench.py), with Drill's
  exact prompt and schema. Once there is a vanilla recording: `wtmate ingest` it, then
  `wtmate bench` with both models as `[[contenders]]`.

## How the models run (Project Prometheus)

Both are GGUF files with a vision projector, served by **llama.cpp's `llama-server`** (the
Unsloth build `b12588-mix`, CUDA 13) on the RTX 5090, one at a time. Settings follow Prometheus's
`tools/assistant_arena/run.py`: all layers on the GPU, flash attention, 16k context.

| | File | Vision | Thinking off? |
| --- | --- | --- | --- |
| Qwen | `models/qwen3.8-27b-huihui-q5/Huihui-Qwen3.8-27B-abliterated-Q5_K.gguf` (19.5 GB) | `mmproj-model-bf16.gguf` | yes, `enable_thinking=false` |
| Inkling 2 Mini | `models/inkling-2-mini-unsloth/Inkling-2-Mini-UD-Q4_K_XL.gguf` (17.6 GB) | `mmproj-F16.gguf` | no, `reasoning_effort=none` is its minimum and still thinks ~1,000 tokens |

Rerun: `python tools/prometheus_bench.py bench/prometheus-2026-11-23 --tag=-v2` (add
`inkling --think-budget 256 --tag=-capped-v2` for the capped run). v1 used the old screen
guide and a coach question without it. Raw answers are in `runs/`,
Claude's reference read in `reference.json`.
