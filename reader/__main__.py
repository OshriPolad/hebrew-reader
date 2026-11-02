"""CLI: python -m reader <url-or-pdf> [-o out.mp3] [--text-only]"""
import argparse
import sys

from dotenv import load_dotenv

from .pipeline import prepare_text, text_to_mp3
from .tts import AzureTTS


def main() -> int:
    p = argparse.ArgumentParser(description="Read a URL or PDF aloud into an MP3.")
    p.add_argument("source", help="Article URL or path to a PDF")
    p.add_argument("-o", "--out", default="output.mp3")
    p.add_argument("--text-only", action="store_true",
                   help="Print the cleaned text instead of calling TTS (free, for checking)")
    args = p.parse_args()

    load_dotenv()
    text = prepare_text(args.source)
    if args.text_only:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
        return 0

    text_to_mp3(text, args.out, AzureTTS.from_env(),
                on_progress=lambda i, n: print(f"\rchunk {i}/{n}", end="", flush=True))
    print(f"\nSaved {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
