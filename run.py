"""CLI: produce a short-drama episode from a one-line premise.

    python run.py "a hawker discovers his rival stole his secret recipe" --lang en --shots 3
    python run.py "..." --fast          # faster wan2.1-t2v-turbo shots
"""
import argparse
import sys
from pathlib import Path

from showrunner.pipeline import produce_episode

# Windows consoles default to cp1252; force UTF-8 so 中文/Malay output prints.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

_HIDE = {"shot", "premise"}


def _log(stage: str, data: dict) -> None:
    parts = ", ".join(f"{k}={v}" for k, v in data.items() if k not in _HIDE)
    print(f"  [{stage}] {parts[:200]}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Qwen Showrunner - premise to episode")
    ap.add_argument("premise", help="one-line story premise")
    ap.add_argument("--lang", default="en", help="spoken language (en, zh, ms, ...)")
    ap.add_argument("--shots", type=int, default=3, help="number of shots/scenes")
    ap.add_argument("--sub-lang", default="en", help="subtitle language (translation)")
    ap.add_argument("--fast", action="store_true", help="use faster wan2.1-t2v-turbo")
    ap.add_argument("--out", default="output", help="output root dir")
    args = ap.parse_args()

    print(f"Producing: \"{args.premise}\"  ({args.lang}, {args.shots} shots, "
          f"{'fast' if args.fast else 'quality'})\n")
    result = produce_episode(
        args.premise, args.lang, args.shots, Path(args.out), args.fast,
        subtitle_lang=args.sub_lang, on_event=_log)
    print(f"\n  EPISODE READY -> {result['episode']}")
    print(f"  {result['title']} — {result['logline']}")


if __name__ == "__main__":
    main()
