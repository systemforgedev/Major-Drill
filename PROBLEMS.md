# Known problems, and how we attack each one

Each problem has a number we track, so we know when it is solved.

## 1. Live calls arrive late or are wrong

A call that comes 3 seconds late can get you killed, and a wrong call teaches you to ignore Drill.

- Built: the call gate (`live.py`) drops calls older than `max_latency_s`, below `min_confidence`,
  too soon after the last call, or repeating a recent one. Drill never queues frames, so it always
  looks at the newest screen.
- Built: Major grades Drill's calls after every match and writes if-then lessons Drill reads next time.
- Next: send only the minimap crop plus a small full frame; try 2B/4B local models; stream the call.
- **Measure:** lag p50/p90 and call accuracy in `wtmate bench --batch 1`. Target: p90 under 2 s,
  accuracy over 60%.

## 2. Reading your position from video

Without the game feed, the heatmap comes from the model reading the minimap grid square. It is coarse
and can be wrong.

- Built: grid reading per frame, heatmap by grid square, flagged as approximate on the page.
- Next: crop the minimap and read it at higher resolution; later a small dedicated detector for the
  player arrow, which can run on CPU.
- **Measure:** grid match rate. Ground truth comes from live-mode matches, where the game's own map
  page gives your exact position for the same moments. Target: 80%.

## 3. Scoring the benchmark

"Good game sense" has no single right answer.

- Built: Major's call grades are the answer key; contenders are scored on call accuracy, death recall,
  minimap reading, talkativeness (calls per minute) and lag. The face-off page shows every model's
  call side by side on the same frames.
- Weakness: Major can be wrong. Next: let you mark Major's calls right or wrong on the page, and use
  your marks as the gold set for the first 20 matches.
- **Measure:** how often your marks agree with Major. Target: 80% before we trust Major alone.

## 4. Gaijin's rules

- Advice from your own screen is fine; ESP-style enemy reveals and input automation are not. wtmate does neither.
- The 2026 terms ban using game content for AI training without written permission. That blocks a
  shared training dataset, not personal reviews. **Next:** write to Gaijin before any data pooling.

## 5. The business case (rough)

- Free and open source: the base tier with your own API key or a local model.
- Paid option later: hosted Major (no key, no setup), a career page synced across PCs, squad reviews.
- Benchmark: a public "game sense" leaderboard of models on the same clips. Only with clips players
  agree to share, and only after the Gaijin question above is settled.
- **Measure first:** do your own numbers improve over 10 matches? If the tool can't help its first
  test subject, nothing else matters.
