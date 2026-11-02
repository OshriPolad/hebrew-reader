"""Source (URL/PDF) -> cleaned text -> MP3."""
from pathlib import Path

from .clean import clean_text
from .extract import extract
from .lang import chunk, segment_by_language


def prepare_text(source: str) -> str:
    raw, kind = extract(source)
    return clean_text(raw, hard_wrapped=(kind == "pdf"))


def text_to_mp3(text: str, out_path: str | Path, tts, on_progress=None) -> None:
    jobs = [(lang, c) for lang, seg in segment_by_language(text) for c in chunk(seg)]
    # MP3 frames with identical encoder settings can be concatenated directly.
    with open(out_path, "wb") as f:
        for i, (lang, c) in enumerate(jobs, 1):
            f.write(tts.synthesize(c, lang))
            if on_progress:
                on_progress(i, len(jobs))
