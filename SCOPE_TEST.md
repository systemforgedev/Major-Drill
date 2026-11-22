# Scope test: version 1 (base tier)

You are test subject #1. Goal: prove that a recording goes in and a useful after-action report
comes out, and that it gets more useful over a few runs. About an hour at your PC.

**Game: Mech Havoc first** (single player, no terms-of-service questions). Add
`game = "profiles/mech_havoc.toml"` to `wtmate.toml`. "Match" below means one run or mission.
The Mech Havoc profile is a draft written without seeing the HUD, so Step 0b fixes it.

Write your answers in the boxes as you go. Each step says what counts as a pass.

## Step 0: setup (10 min)

- [ ] Follow Install in the README. Run `wtmate check`.
  **Pass:** Python, ffmpeg, ffprobe and Claude all show `ok`. (Live-mode lines can be `!!`.)
- [ ] Run `wtmate --mock review <any short video>`.
  **Pass:** a review page opens with video, timeline, heatmap grid and a mock AAR. No API cost.

## Step 0b: fix the Mech Havoc profile (10 min)

- [ ] Take 3 screenshots of Mech Havoc in combat, at low health, and on the death screen.
- [ ] Compare them with `screen_guide` in `profiles/mech_havoc.toml`. Fix anything wrong (what the
  bars are called, whether there is a radar or minimap) and adjust `calls` to what you'd want shouted.
  Or send the screenshots over and we'll fix it together.

## Step 1: first real review (15 min)

- [ ] Record one full Mech Havoc run (ShadowPlay, OBS or Game Bar).
- [ ] `wtmate review <file>`
  **Pass:** finishes without errors. Write down how long it took: ______ min.
- [ ] Check usage/cost in your Anthropic console. Cost for this match: ______
  **Pass:** under $0.50 per 15 minutes of footage.

## Step 2: is the review true? (10 min)

Open the review page and click through the timeline.

- [ ] Deaths on the timeline vs. real deaths. Real: ____ Found: ____
  **Pass:** at least 2 of 3 real deaths found, and no more than 1 fake death.
- [ ] Situation readings: pause on 5 random moments and check the line under the video (situation and threat).
  Right: ____ / 5. **Pass:** 3 of 5 or better.
- [ ] Read the 3 "fix next match" items.
  **Pass:** you agree with at least 2 of 3. Which one was wrong? ______

## Step 3: does it remember? (3 more matches, any time)

- [ ] Review 3 more runs the same way.
- [ ] `wtmate plan`
  **Pass:** the career page (`matches/mech_havoc/index.html`) shows repeat mistakes with counts, and the plan
  names at least one habit or spot where you keep dying that you recognise.
- [ ] Play 2 matches trying the plan's first focus area, review them.
  **Pass (stretch):** that mistake's count per match goes down.

## Step 4: optional face-off (5 min)

- [ ] Add a local model as a `[[contenders]]` entry (see `wtmate.example.toml`), then
  `wtmate bench latest --limit 40`.
  **Pass:** the face-off page opens with a score row per model. Note the lag p50: ______ s.
  Under 2 s at `--batch 1` means that model is a live Drill candidate.

## What to send back

Your answers above, plus `matches/<match>/debrief.json` for the match where the AAR felt most
wrong. That file is the fastest way to tune Major's prompt.
