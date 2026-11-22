# Setup on Windows (no API key)

About 15 minutes. Open **PowerShell** and run these one at a time.

## 1. Tools

```powershell
winget install Python.Python.3.12
winget install Gyan.FFmpeg
winget install Git.Git
```

Close and reopen PowerShell so the new commands are found.

## 2. Major Drill

```powershell
cd $HOME
git clone https://github.com/systemforgedev/major-drill
cd major-drill
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[live]"
wtmate --game profiles/mech_havoc.toml check
```

Every line should say `ok`, except the optional ones marked `--`.

To avoid typing `--game ...` every time, create `wtmate.toml` in the folder with:

```toml
game = "profiles/mech_havoc.toml"
```

## 3. Try it

```powershell
wtmate protocols test path\to\a_mech_havoc_screenshot.png     # what Drill reads and would say
wtmate review path\to\a_recording.mp4                         # timeline + review page, all local
wtmate live                                                   # Drill talks while you play (Ctrl+C to stop)
```

Record with ShadowPlay (Alt+F9) or Xbox Game Bar (Win+Alt+R). Run Mech Havoc in **borderless
windowed** or windowed mode so screen capture sees it.

## 4. Optional: read HP and ammo numbers (OCR)

Without this, the HP and ammo protocols stay quiet. Everything else works.

```powershell
winget install UB-Mannheim.TesseractOCR
pip install -e ".[ocr]"
```

`wtmate check` should now say `OCR ... found`.

## 5. Optional: a local vision model ("kev")

kev is a small AI model that runs on your own graphics card, free and offline. It describes each
frame (where the enemies are, whether there's a big one) and the protocols decide what to say.
Your GPU has plenty of room for a 7-8B model next to the game.

**With Ollama** (simplest):

```powershell
winget install Ollama.Ollama
ollama pull qwen2.5vl:7b
```

**If kev is already in LM Studio**: load it, open the Developer tab and start the server
(it listens on `http://127.0.0.1:1234/v1`).

Then add to `wtmate.toml`:

```toml
[vision]
provider = "openai_compat"
base_url = "http://127.0.0.1:11434/v1"   # LM Studio: http://127.0.0.1:1234/v1
model = "qwen2.5vl:7b"                    # or kev's model name as the server lists it
timeout_s = 3

[live]
frame_every_s = 1.0
```

`wtmate check` tests the server. If calls come late, use a smaller model (e.g. `qwen2.5vl:3b`)
or switch `[vision]` back to `provider = "none"`; the rules keep working either way.
