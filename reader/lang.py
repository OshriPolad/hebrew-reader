"""Language detection per paragraph and chunking for the TTS API."""
import re

HEBREW = re.compile(r"[\u0590-\u05FF]")
LATIN = re.compile(r"[A-Za-z]")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def detect(paragraph: str) -> str | None:
    he, en = len(HEBREW.findall(paragraph)), len(LATIN.findall(paragraph))
    if he == en == 0:
        return None
    return "he" if he >= en else "en"


def segment_by_language(text: str, default: str = "he") -> list[tuple[str, str]]:
    """Group consecutive paragraphs of the same language: [(lang, text), ...]."""
    segments: list[tuple[str, list[str]]] = []
    for para in text.split("\n\n"):
        if not para.strip():
            continue
        lang = detect(para) or (segments[-1][0] if segments else default)
        if segments and segments[-1][0] == lang:
            segments[-1][1].append(para)
        else:
            segments.append((lang, [para]))
    return [(lang, "\n\n".join(paras)) for lang, paras in segments]


def _units(para: str, max_chars: int) -> list[str]:
    if len(para) <= max_chars:
        return [para]
    out = []
    for sentence in SENTENCE_SPLIT.split(para):
        while len(sentence) > max_chars:
            cut = sentence.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            out.append(sentence[:cut])
            sentence = sentence[cut:].lstrip()
        if sentence:
            out.append(sentence)
    return out


def chunk(text: str, max_chars: int = 3000) -> list[str]:
    """Split text into chunks <= max_chars at paragraph, then sentence boundaries."""
    chunks, current = [], ""
    for para in text.split("\n\n"):
        for unit in _units(para, max_chars):
            sep = "\n\n" if current else ""
            if len(current) + len(sep) + len(unit) > max_chars:
                chunks.append(current)
                current = unit
            else:
                current += sep + unit
    if current:
        chunks.append(current)
    return chunks
