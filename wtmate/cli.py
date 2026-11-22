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
    line(sys.version_info >= (3, 11), f"Python {sys.version.split()[0]}", "install Python 3.11 or newer")
    line(bool(shutil.which(cfg.ffmpeg)), "ffmpeg", "install ffmpeg and make sure it is on PATH")
    line(bool(shutil.which(cfg.ffprobe)), "ffprobe", "comes with ffmpeg")
    for label, m in (("Drill", cfg.fast), ("Major", cfg.deep)):
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
    from .major import debrief_match
    from .review import build_index, build_review

    print(f"[ingest] {args.video}")
    match = ingest_video(cfg, args.video, args.label or "", copy=not args.no_copy)
    print(f"[ingest] {len(match.frames())} frames -> {match.root}")
    memory = Memory(cfg.matches_dir)
    stats = observe_match(match, make_provider(cfg.fast), memory, cfg.ingest.batch_size, _progress)
    print(f"[drill] done: {stats}")
    if not args.no_debrief:
        print(f"[major] reviewing with {cfg.deep.model} (this can take a minute)...")
        d = debrief_match(match, make_provider(cfg.deep), memory)
        print("[major] fix next match:")
        for i, s in enumerate(d.get("top3", []), 1):
            print(f"   {i}. {s}")
    page = build_review(match, cfg.live.min_confidence)
    build_index(cfg.matches_dir)
    _open(page, args.no_open)


def cmd_debrief(cfg, args):
    from .major import debrief_match
    from .review import build_index, build_review

    match = _match(cfg, args.match)
    d = debrief_match(match, make_provider(cfg.deep), Memory(cfg.matches_dir))
    for i, s in enumerate(d.get("top3", []), 1):
        print(f"{i}. {s}")
    build_review(match, cfg.live.min_confidence)
    build_index(cfg.matches_dir)


def cmd_plan(cfg, args):
    from .major import plan_improvement
    from .review import build_index

    plan = plan_improvement(cfg.matches_dir, make_provider(cfg.deep), Memory(cfg.matches_dir))
    print(plan["headline"])
    for f in plan["focus_areas"]:
        print(f"- {f['goal']}: {f['practice']} (measure: {f['measure']})")
    print(f"Drill now has {len(plan['drill_lessons'])} lessons.")
    build_index(cfg.matches_dir)


def cmd_live(cfg, args):
    from .live import run_live
    from .major import debrief_match
    from .review import build_index, build_review

    memory = Memory(cfg.matches_dir)
    match = run_live(cfg, make_provider(cfg.fast), memory,
                     max_duration_s=args.minutes * 60 if args.minutes else None)
    if not args.no_debrief and match.frames():
        print("[major] reviewing...")
        debrief_match(match, make_provider(cfg.deep), memory)
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


def main(argv=None):
    ap = argparse.ArgumentParser(prog="wtmate", description="War Thunder AI teammate: Drill (fast) and Major (deep).")
    ap.add_argument("--config", help="path to wtmate.toml (default: ./wtmate.toml if present)")
    ap.add_argument("--mock", action="store_true", help="use fake models: free dry run, no API calls")
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

    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    if args.mock:
        cfg.fast.provider = cfg.deep.provider = "mock"
        for c in cfg.contenders:
            c["provider"] = "mock"
    {"check": cmd_check, "review": cmd_review, "debrief": cmd_debrief, "plan": cmd_plan,
     "live": cmd_live, "bench": cmd_bench, "pages": cmd_pages}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
