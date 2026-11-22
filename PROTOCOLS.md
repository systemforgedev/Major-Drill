# Protocols: teaching Drill without training an AI

A **protocol** is one plain rule: *in this situation, say this, and it's this important.*
Drill reads the screen, checks every protocol, and says the most important one that fits.

```toml
[[protocol]]
id = "right-flank"
priority = 2                                   # 1 = most important; lower number wins
when = ["in_mission", "enemies_right >= 1", "enemies_right > enemies_front"]
call = "watch your flank"                      # one of the game profile's calls
say = "Enemies on your right flank"            # what Drill says out loud
why = "More minimap enemies to the right than ahead"
cooldown_s = 20                                # don't repeat within 20 seconds
```

No API key, no internet, no training. It runs on any PC in a few milliseconds per frame.
The Mech Havoc starter set is [`protocols/mech_havoc.toml`](protocols/mech_havoc.toml).

## Where the facts come from

Protocols check **facts**. Facts come from three places, cheapest first:

1. **HUD readers** (`[[detector]]` in the protocol file). No AI. They look at one box of the
   screen: how full a bar is, whether a colour is there ("Extraction Available!" is yellow),
   how many red dots are on the minimap and on which side of you. Numbers like HP and ammo are
   read with OCR (Tesseract, a free install; optional).
2. **A local vision model** ("kev", optional). It looks at the frame and fills in things the HUD
   can't tell you: the situation, which side the enemies on screen are, whether there's a big
   enemy. It only *describes*; the protocols still decide what to say. Where both have a value,
   the HUD reader wins because it's exact.
3. **The engine itself**: `t` (seconds), `<fact>_max` (highest value seen this session, so
   `hp / hp_max` works without knowing the mech's max HP), and `d_<fact>` (change over the last
   ~3 seconds, so `d_hp_pct < -0.2` means "just lost a fifth of your HP").

A fact nobody could read (no OCR, no vision model) makes its condition false, so a protocol never
fires on a guess. That is why the starter set works with nothing installed: the HP and ammo rules
just stay quiet until OCR is there.

## Writing conditions

| Write | Means |
| --- | --- |
| `hp_pct < 0.35` | a number compared with `<` `<=` `>` `>=` `==` `!=` |
| `threat_side == 'right'` | text (any case) |
| `enemies_right > enemies_front` | one fact against another |
| `mortar_ready` / `not in_mission` | yes/no facts |

`when = [...]`: all must be true. `when_any = [...]`: at least one. Use both if you like.

Other protocol fields, all optional:

| Field | What it does |
| --- | --- |
| `hold_s` | the situation must last this long first (e.g. 4 s standing still) |
| `cooldown_s` | quiet time before this protocol may fire again (default 20) |
| `situation` | label for the timeline, one of the profile's situations |
| `event` | logged when it starts, e.g. `big hit taken`, `death` |
| `mistake` | counted as this mistake in the free review (one of the profile's categories) |
| `tip` | the fix, shown in the review's "fix next time" list |
| `good` | a good play to praise in the review |
| `enabled = false` | switch it off without deleting it |

Priority 1 protocols may interrupt Drill's quiet gap (by default Drill waits 6 s between calls).
Keep priority 1 for "you're about to die" calls.

## Checking and tuning

```
wtmate --game profiles/mech_havoc.toml protocols check            # typos, unknown calls or facts
wtmate --game profiles/mech_havoc.toml protocols test shot1.png    # every fact it read + what Drill would say
```

Take a few screenshots (F12 in Steam, or Win+Shift+S) in different moments: full HP, low HP,
enemies around, call-in recharging, extraction open. Run `protocols test` on each. If a fact is
wrong, move its `box` (fractions of the screen: left, top, right, bottom) or change its `colour`
and `tolerance`. Each detector has a `note` saying what it read on the reference screenshot.

## Getting better protocols from a Claude chat (no API key)

1. Play, record the run, then `wtmate --game profiles/mech_havoc.toml review run.mp4`.
2. `wtmate --game profiles/mech_havoc.toml label latest` and mark each call right (y) or wrong (n).
3. `wtmate --game profiles/mech_havoc.toml brief latest` writes `brief.md` in the match folder:
   what fired, what you marked wrong, the timeline and the current protocol file.
4. Paste `brief.md` into a Claude chat with a short clip or a few screenshots of the moments that
   went badly. Ask for the updated protocol file.
5. Save the reply over `protocols/mech_havoc.toml`, run `protocols check`, done.

Your Claude subscription covers the chat, so nothing extra to set up.

## Rules now, a trained model later

Protocols are the right start: you can read every rule, fix a bad one in a minute, and they need
no data. Their limit is that someone has to write each rule and each HUD box.

A trained model (a small neural network) is the other way round: it learns the patterns itself,
but it needs a lot of labelled examples and you can't easily see why it said something.

The two fit together. Every time a protocol fires, Drill saves the frame and the facts to
`firings.jsonl` (and `firings/`), and `wtmate label` adds your right/wrong mark. After enough
sessions, that folder is a ready training set for a small local model that learns *your*
protocols plus your corrections. That's a later phase; the logging is already on.

For Mech Havoc that's fine. For War Thunder, Gaijin's 2026 terms say game content may not be used
for AI training without their written permission, so for War Thunder keep the labels to tuning
protocols until there's a written OK.

## Turning on a local vision model ("kev")

kev is itself a small AI model, just one that runs on your own GPU for free instead of in the
cloud. It's optional: the protocols work without it. See [SETUP_WINDOWS.md](SETUP_WINDOWS.md)
for the steps; the config is:

```toml
[vision]
provider = "openai_compat"
base_url = "http://127.0.0.1:11434/v1"   # Ollama (LM Studio: http://127.0.0.1:1234/v1)
model = "qwen2.5vl:7b"                    # or the name kev has in your server
timeout_s = 3
```

## Cloud (later, optional)

Everything Claude-based is still there. In `wtmate.toml`: `drill = "model"` makes a model pick the
calls (`[fast]`), `major = "model"` makes a model write the review and the cross-match plan
(`[deep]`). Both need `pip install anthropic` and an API key.
