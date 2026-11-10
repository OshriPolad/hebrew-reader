"""CLI: python -m reader <url-or-pdf> [-o out.mp3] [--text-only]"""
import argparse
import sys

from dotenv import load_dotenv

import os

from .ocr import AzureOCR
from .pipeline import prepare_text, text_to_mp3
from .tts import AzureTTS


class _CliOCR:
    """No budget tracking in the CLI: just print how many pages will be scanned."""

    def __init__(self):
        self.client = AzureOCR.from_env()

    def reserve(self, pages):
        print(f"Scanning {pages} page(s) with OCR...", file=sys.stderr)

    def read_image(self, image):
        return self.client.read_image(image)


def main() -> int:
    p = argparse.ArgumentParser(description="Read a URL or PDF aloud into an MP3.")
    p.add_argument("source", help="Article URL, or a PDF / Word / image file")
    p.add_argument("-o", "--out", default="output.mp3")
    p.add_argument("--text-only", action="store_true",
                   help="Print the cleaned text instead of calling TTS (free, for checking)")
    args = p.parse_args()

    load_dotenv()
    ocr = _CliOCR() if os.getenv("AZURE_DOCINTEL_ENDPOINT") and os.getenv("AZURE_DOCINTEL_KEY") else None
    text = prepare_text(args.source, ocr)
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
