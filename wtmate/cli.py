"""Command line: `wtmate <command>`. Run `wtmate -h` for the list."""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import webbrowser
from pathlib import Path

from .config import load_config
from .match import Match
from .memory import Memory
from .models import make_provider
from .profiles import BUILTIN, load_profile


def _match(cfg, ref: str) -> Match:
    p = Path(ref)
    if not p.exists():
        p = Path(cfg.matches_dir) / ref
    if ref == "latest":
        root = Path(cfg.matches_dir)
        dirs = sorted(d for d in root.iterdir() if d.is_dir() and (d / "meta.json").exists()) if root.exists() else []
        if not dirs:
            sys.exit("No matches yet.")
        p = dirs[-1]
    if not (p / "meta.json").exists():
        sys.exit(f"Not a match folder: {ref}")
    return Match(p)


def _protocol_file(cfg, profile) -> Path:
    if cfg.protocols:
        return Path(cfg.protocols)
    # Look next to the working folder first, then next to the installed package.
    for base in (Path.cwd(), Path(__file__).resolve().parent.parent):
        p = base / "protocols" / f"{profile.key}.toml"
        if p.exists():
            return p
    return Path("protocols") / f"{profile.key}.toml"


def _protocol_set(cfg, profile, strict=True):
    from .protocols import load_protocols

    path = _protocol_file(cfg, profile)
    if not path.exists():
        sys.exit(f"No protocol file for {profile.key} at {path}. Copy protocols/mech_havoc.toml as a start, "
                 "or set drill = \"model\" in wtmate.toml to use a model instead.")
    pset = load_protocols(path)
    problems = pset.validate(profile)
    if problems and strict:
        sys.exit("Protocol file problems:\n  " + "\n  ".join(problems))
    return pset


def _local_drill(cfg, profile):
    from .local import LocalDrill

    pset = _protocol_set(cfg, profile)
    vision = make_provider(cfg.vision)
    drill = LocalDrill(profile, pset, vision)
    print(f"[drill] protocols: {len(pset.protocols)} rules from {pset.path}; "
          f"vision model: {cfg.vision.model if vision else 'off (rules only)'}; "
          f"OCR: {'on' if drill.hud.ocr else 'off (install Tesseract to read HP and ammo)'}")
    return drill, pset


def _run_major(cfg, match, memory, profile, pset=None):
    """Write the debrief: locally from the protocols (default) or with a model."""
    if cfg.major == "local":
        from .local_major import local_debrief

        return local_debrief(match, pset or _protocol_set(cfg, profile), memory)
    from .major import debrief_match

    print(f"[major] reviewing with {cfg.deep.model} (this can take a minute)...")
    return debrief_match(match, make_provider(cfg.deep), memory, profile)


def _progress(done, total):
    print(f"\r[drill] {done}/{total} frames", end="" if done < total else "\n", flush=True)


def _open(path: Path, no_open: bool):
    print(f"Open: {path.resolve()}")
    if not no_open:
        webbrowser.open(path.resolve().as_uri())


def cmd_check(cfg, args):
    ok = True

    def line(good, what, hint=""):
        nonlocal ok
        ok &= good
        print(f"  [{'ok' if good else '!!'}] {what}" + (f"  -> {hint}" if hint and not good else ""))

    print("wtmate environment check")
    try:
        p = load_profile(cfg.game)
        line(True, f"game profile: {p.title}")
    except Exception as e:
        line(False, f"game profile {cfg.game!r}", str(e))
    line(sys.version_info >= (3, 11), f"Python {sys.version.split()[0]}", "install Python 3.11 or newer")
    line(bool(shutil.which(cfg.ffmpeg)), "ffmpeg", "install ffmpeg and make sure it is on PATH")
    line(bool(shutil.which(cfg.ffprobe)), "ffprobe", "comes with ffmpeg")
    used = []
    if cfg.drill == "protocols":
        try:
            prof = load_profile(cfg.game)
            path = _protocol_file(cfg, prof)
            from .protocols import load_protocols

            pset = load_protocols(path)
            probs = pset.validate(prof)
            line(not probs, f"Drill: protocols ({len(pset.protocols)} rules, {path})", "; ".join(probs[:3]))
        except SystemExit as e:
            line(False, "Drill: protocol file", str(e))
        except Exception as e:
            line(False, "Drill: protocol file", str(e))
        from .hud import ocr_available

        print(f"  [--] OCR for HP and ammo numbers: {'found' if ocr_available() else 'not installed (optional, see SETUP_WINDOWS.md)'}")
        if cfg.vision.provider != "none":
            used.append(("Vision (kev)", cfg.vision))
    else:
        used.append(("Drill", cfg.fast))
    if cfg.major == "local":
        line(True, "Major: local review from protocols (no API key needed)")
    else:
        used.append(("Major", cfg.deep))
    for label, m in used:
        if m.provider == "openai_compat":
            import urllib.request

            try:
                urllib.request.urlopen(m.base_url.rstrip("/") + "/models", timeout=3).read()
                line(True, f"{label}: local server at {m.base_url} ({m.model})")
            except Exception:
                line(False, f"{label}: local server at {m.base_url}", "start Ollama or LM Studio (see SETUP_WINDOWS.md)")
            continue
        if m.provider == "anthropic":
            try:
                import anthropic  # noqa: F401
                has_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
                line(has_key, f"{label}: Claude ({m.model})",
                     "set ANTHROPIC_API_KEY (or run `ant auth login`, then ignore this line)")
            except ImportError:
                line(False, f"{label}: anthropic package", "pip install anthropic")
        else:
            line(True, f"{label}: {m.provider} ({m.model})")
    try:
        import mss  # noqa: F401
        line(True, "screen capture (mss) for live mode")
    except ImportError:
        line(False, "screen capture (mss) for live mode", "pip install mss (only needed for live mode)")
    try:
        import pyttsx3  # noqa: F401
        line(True, "voice (pyttsx3) for live mode")
    except ImportError:
        line(False, "voice (pyttsx3) for live mode", "pip install pyttsx3 (only needed for live mode)")
    from .telemetry import Telemetry
    t = Telemetry(cfg.telemetry.url)
    print(f"  [--] game map feed at {cfg.telemetry.url}: "
          f"{'found' if t.available() else 'not running (normal unless War Thunder is open)'}")
    print("All good." if ok else "Fix the lines marked !! (live-mode lines are optional).")


def cmd_review(cfg, args):
    """The core flow: recording in, review page out."""
    from .drill import observe_match
    from .ingest import ingest_video
    from .review import build_index, build_review

    print(f"[ingest] {args.video}")
    match = ingest_video(cfg, args.video, args.label or "", copy=not args.no_copy)
    print(f"[ingest] {len(match.frames())} frames -> {match.root}")
    memory = Memory(cfg.matches_dir)
    profile = load_profile(cfg.game)
    pset = None
    if cfg.drill == "protocols":
        from .local import observe_match_local

        drill, pset = _local_drill(cfg, profile)
        stats = observe_match_local(match, drill, _progress)
    else:
        stats = observe_match(match, make_provider(cfg.fast), memory, profile, cfg.ingest.batch_size, _progress)
    print(f"[drill] done: {stats}")
    if not args.no_debrief:
        d = _run_major(cfg, match, memory, profile, pset)
        print("[major] fix next time:")
        for i, s in enumerate(d.get("top3", []), 1):
            print(f"   {i}. {s}")
    page = build_review(match, cfg.live.min_confidence)
    build_index(cfg.matches_dir)
    _open(page, args.no_open)


def cmd_debrief(cfg, args):
    from .review import build_index, build_review

    match = _match(cfg, args.match)
    d = _run_major(cfg, match, Memory(cfg.matches_dir), load_profile(cfg.game))
    for i, s in enumerate(d.get("top3", []), 1):
        print(f"{i}. {s}")
    build_review(match, cfg.live.min_confidence)
    build_index(cfg.matches_dir)


def cmd_plan(cfg, args):
    if cfg.major == "local":
        sys.exit("`plan` needs a model (major = \"model\"). Without a key: run `wtmate brief latest` and "
                 "paste the brief plus a clip into a Claude chat to get new protocols.")
    from .major import plan_improvement
    from .review import build_index

    plan = plan_improvement(cfg.matches_dir, make_provider(cfg.deep), Memory(cfg.matches_dir), load_profile(cfg.game))
    print(plan["headline"])
    for f in plan["focus_areas"]:
        print(f"- {f['goal']}: {f['practice']} (measure: {f['measure']})")
    print(f"Drill now has {len(plan['drill_lessons'])} lessons.")
    build_index(cfg.matches_dir)


def cmd_live(cfg, args):
    from .live import run_live
    from .review import build_index, build_review

    memory = Memory(cfg.matches_dir)
    profile = load_profile(cfg.game)
    pset = None
    if cfg.drill == "protocols":
        drill, pset = _local_drill(cfg, profile)
    else:
        drill = make_provider(cfg.fast)
    match = run_live(cfg, drill, memory, profile,
                     max_duration_s=args.minutes * 60 if args.minutes else None)
    if not args.no_debrief and match.frames():
        print("[major] reviewing...")
        _run_major(cfg, match, memory, profile, pset)
    page = build_review(match, cfg.live.min_confidence)
    build_index(cfg.matches_dir)
    _open(page, args.no_open)


def cmd_bench(cfg, args):
    from .bench import run_bench

    match = _match(cfg, args.match)
    results = run_bench(cfg, match, args.batch, args.limit, args.only)
    for name, s in results.items():
        print(f"{name}: {s}")
    _open(match.root / "bench" / "compare.html", args.no_open)


def cmd_pages(cfg, args):
    from .review import all_matches, build_index, build_review

    for m in all_matches(cfg.matches_dir):
        build_review(m, cfg.live.min_confidence)
    _open(build_index(cfg.matches_dir), args.no_open)


def cmd_protocols(cfg, args):
    from .local import LocalDrill

    profile = load_profile(cfg.game)
    pset = _protocol_set(cfg, profile, strict=False)
    problems = pset.validate(profile)
    if args.action == "check":
        known = pset.known_facts()
        for p in pset.protocols:
            unknown = sorted(f for f in p.facts_used if f not in known and not f.endswith("_max"))
            flag = f"  !! unknown facts: {unknown}" if unknown else ""
            print(f"  p{p.priority} {p.id:24} -> {p.call!r}{'' if p.enabled else ' (off)'}{flag}")
        print("\n".join(["Problems:"] + problems) if problems else f"OK: {len(pset.protocols)} protocols, "
              f"{len(pset.detectors)} detectors in {pset.path}")
        return
    # test: run the detectors and protocols over screenshots
    drill = LocalDrill(profile, pset, make_provider(cfg.vision))
    if drill.hud.skipped:
        print(f"(OCR not installed, skipped: {', '.join(drill.hud.skipped)})")
    for i, img in enumerate(args.images):
        o = drill.observe(float(i * cfg.live.frame_every_s), Path(img).read_bytes())
        print(f"== {img}")
        for k, v in sorted(o["facts"].items()):
            if not k.startswith("d_") and not k.endswith("_max"):
                print(f"   {k} = {v}")
        print(f"   -> fired: {', '.join(o['fired']) or 'nothing'}")
        print(f"   -> Drill says: {o['say'] or '(nothing)'}  [{o['protocol'] or '-'}]  situation: {o['situation']}")


def cmd_label(cfg, args):
    from .local import label_firings

    match = _match(cfg, args.match)
    show = None
    if not args.no_open:
        show = lambda p: webbrowser.open(p.resolve().as_uri())  # noqa: E731
    done = label_firings(match, show=show)
    print(f"Labelled {done['right']} right, {done['wrong']} wrong in {match.root / 'firings.jsonl'}")


def cmd_brief(cfg, args):
    """Write a brief to paste into a Claude chat (no API key) to get better protocols."""
    from collections import Counter

    match = _match(cfg, args.match)
    profile = load_profile(cfg.game)
    path = _protocol_file(cfg, profile)
    obs, firings = match.read("observations"), match.read("firings")
    d = match.read_json("debrief.json", {}) or {}
    labels = Counter((f["protocol"], f.get("label")) for f in firings)
    lines = [f"# Major Drill brief: {match.id}", "",
             "Please review this run with me and update my protocol file. I'll attach a clip or screenshots.",
             "Reply with the full updated protocol file (TOML, same format) and a short list of what changed.",
             "Only use these calls: " + ", ".join(profile.calls),
             "Situations: " + ", ".join(profile.situations),
             "Mistake categories: " + ", ".join(profile.mistakes), "",
             "## What the protocols did this run", d.get("summary", "(no review yet)"), ""]
    for pid, n in Counter(f["protocol"] for f in firings).most_common():
        lines.append(f"- {pid}: fired {n}x (marked right {labels[(pid, 'right')]}, wrong {labels[(pid, 'wrong')]})")
    wrong = [f for f in firings if f.get("label") == "wrong"]
    if wrong:
        lines += ["", "## Calls I marked wrong"]
        lines += [f"- t={f['t']:.0f}s {f['protocol']}: {f.get('note') or '(no note)'}" for f in wrong]
    lines += ["", "## Timeline (t, situation, call)"]
    lines += [f"- {o['t']:.0f}s {o.get('situation','')}: {o.get('say') or o.get('call')}" for o in obs
              if o.get("call", "none") != "none" or o.get("event", "none") != "none"][:200]
    lines += ["", f"## Current protocol file ({path.name})", "```toml",
              path.read_text(encoding="utf-8") if path.exists() else "(missing)", "```"]
    out = match.root / "brief.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Brief written: {out.resolve()}\nPaste it into a Claude chat with a clip of the run.")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="wtmate", description="AI game teammate: Drill (fast calls) and Major (deep review).")
    ap.add_argument("--config", help="path to wtmate.toml (default: ./wtmate.toml if present)")
    ap.add_argument("--game", help=f"game profile: {', '.join(BUILTIN)}, or a .toml path (overrides the config)")
    ap.add_argument("--mock", action="store_true", help="test the model path with fake models (no calls)")
    ap.add_argument("--no-open", action="store_true", help="don't open pages in the browser")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="check that everything is installed")
    p = sub.add_parser("review", help="CORE: review a recording you made (any video file)")
    p.add_argument("video")
    p.add_argument("--label", help="short name for the match folder")
    p.add_argument("--no-debrief", action="store_true", help="only run Drill, skip Major")
    p.add_argument("--no-copy", action="store_true", help="don't copy the video into the match folder")
    p = sub.add_parser("debrief", help="(re)run Major on a match folder or 'latest'")
    p.add_argument("match")
    sub.add_parser("plan", help="Major's improvement plan across all reviewed matches; rewrites Drill's lessons")
    p = sub.add_parser("live", help="OPTIONAL: Drill watches your screen and talks during a match")
    p.add_argument("--minutes", type=float, help="stop after this many minutes")
    p.add_argument("--no-debrief", action="store_true")
    p = sub.add_parser("bench", help="compare Drill candidates (different models) on one match")
    p.add_argument("match")
    p.add_argument("--batch", type=int, default=1, help="frames per request (1 = live-like latency)")
    p.add_argument("--limit", type=int, help="only the first N frames (cheaper)")
    p.add_argument("--only", nargs="*", help="only contenders whose name contains one of these")
    sub.add_parser("pages", help="rebuild all review pages and the career page")
    p = sub.add_parser("protocols", help="check the protocol file, or test it on screenshots")
    p.add_argument("action", choices=["check", "test"])
    p.add_argument("images", nargs="*", help="screenshots for `test`")
    p = sub.add_parser("label", help="mark each protocol firing right or wrong (training data for later)")
    p.add_argument("match")
    p = sub.add_parser("brief", help="write a brief to paste into a Claude chat to improve the protocols")
    p.add_argument("match")

    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    if args.game:
        cfg.game = args.game
    # Each game keeps its own matches, habits and lessons.
    cfg.matches_dir = str(Path(cfg.matches_dir) / load_profile(cfg.game).key)
    if args.mock:  # fake models: exercise the model path for free
        cfg.drill, cfg.major = "model", "model"
        cfg.fast.provider = cfg.deep.provider = "mock"
        for c in cfg.contenders:
            c["provider"] = "mock"
    {"check": cmd_check, "review": cmd_review, "debrief": cmd_debrief, "plan": cmd_plan,
     "live": cmd_live, "bench": cmd_bench, "pages": cmd_pages, "protocols": cmd_protocols,
     "label": cmd_label, "brief": cmd_brief}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
