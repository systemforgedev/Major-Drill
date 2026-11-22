# Scope test: version 1 (base tier)

You are test subject #1. Goal: prove that a recording goes in and a useful after-action report
comes out, and that it gets more useful over a few matches. About an hour at your PC.

Write your answers in the boxes as you go. Each step says what counts as a pass.

## Step 0: setup (10 min)

- [ ] Follow Install in the README. Run `wtmate check`.
  **Pass:** Python, ffmpeg, ffprobe and Claude all show `ok`. (Live-mode lines can be `!!`.)
- [ ] Run `wtmate --mock review <any short video>`.
  **Pass:** a review page opens with video, timeline, heatmap grid and a mock AAR. No API cost.

## Step 1: first real review (15 min)

- [ ] Record one normal ground battle (ShadowPlay, OBS or Game Bar), full match.
- [ ] `wtmate review <file>`
  **Pass:** finishes without errors. Write down how long it took: ______ min.
- [ ] Check usage/cost in your Anthropic console. Cost for this match: ______
  **Pass:** under $0.50 per 15-minute match.

## Step 2: is the review true? (10 min)

Open the review page and click through the timeline.

- [ ] Deaths on the timeline vs. real deaths. Real: ____ Found: ____
  **Pass:** at least 2 of 3 real deaths found, and no more than 1 fake death.
- [ ] Minimap readings: pause on 5 random moments, compare the grid square shown under the video to the minimap.
  Right: ____ / 5. **Pass:** 3 of 5 or better.
- [ ] Read the 3 "fix next match" items.
  **Pass:** you agree with at least 2 of 3. Which one was wrong? ______

## Step 3: does it remember? (3 more matches, any time)

- [ ] Review 3 more matches the same way.
- [ ] `wtmate plan`
  **Pass:** the career page (`matches/index.html`) shows repeat mistakes with counts, and the plan
  names at least one place or habit where you keep dying that you recognise.
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
