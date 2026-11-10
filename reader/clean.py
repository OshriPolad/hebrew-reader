"""Turn extracted text into clean paragraphs that read smoothly aloud."""
import re
import unicodedata
from collections import Counter

SENTENCE_END = tuple(".!?:;\"'”…)")
PAGE_NUMBER = re.compile(
    r"^\s*(?:page|עמוד|עמ['׳]?)?\s*\d+\s*(?:/\s*\d+|of\s+\d+|מתוך\s+\d+)?\s*$",
    re.IGNORECASE,
)
LEADING_PUNCT = re.compile(r"^([.,:;!?]+)\s*(.*[\u0590-\u05FF].*)$")
# --- Make text "speakable": only words + natural pauses, no symbols read aloud ---
HEB_LETTER = "\u05D0-\u05EA"
URL = re.compile(r"https?://\S+|www\.\S+")
CITATION = re.compile(r"\[[^\]]{0,20}\]")  # [1], [2][3], [עריכה], [דרוש מקור]
OPEN_BRACKET = re.compile(r"\s*[(\[{]\s*")
CLOSE_BRACKET = re.compile(r"\s*[)\]}]\s*")
DASH = re.compile(r"\s+[–—-]+\s+|\s*[–—]\s*")  # standalone dash; keeps maqaf/hyphen inside words
# Quote marks, except gershayim inside abbreviations like צה"ל / ארה״ב
QUOTES = re.compile(
    rf'(?<![{HEB_LETTER}])["״“”„«»]|["״“”„«»](?![{HEB_LETTER}])'
)
SINGLE_QUOTE = re.compile(rf"(?<![A-Za-z{HEB_LETTER}])['‘’]")  # keeps geresh: ג'ירפה, don't
SYMBOLS = re.compile(r"[*#•●▪■◆►|_~^\\<>=/]")
SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?…])")
REPEATED_PAUSES = re.compile(r"([,;:])(?:\s*[,;:])+")
COMMA_BEFORE_END = re.compile(r"[,;:]\s*([.!?…])")
COMMA_AFTER_END = re.compile(r"([.!?…])\s*[,;:]")


def speakable(paragraph: str) -> str:
    """
    Remove anything a TTS voice would read as a symbol name ("סוגריים", "כוכבית"...)
    while keeping every word. Brackets/dashes become commas so the voice pauses.
    """
    p = URL.sub(" ", paragraph)
    p = CITATION.sub("", p)
    p = OPEN_BRACKET.sub(", ", p)
    p = CLOSE_BRACKET.sub(", ", p)
    p = DASH.sub(", ", p)
    p = QUOTES.sub("", p)
    p = SINGLE_QUOTE.sub("", p)
    p = SYMBOLS.sub(" ", p)
    p = SPACE_BEFORE_PUNCT.sub(r"\1", p)
    p = REPEATED_PAUSES.sub(r"\1", p)
    p = COMMA_BEFORE_END.sub(r"\1", p)
    p = COMMA_AFTER_END.sub(r"\1", p)
    p = re.sub(r"\s{2,}", " ", p).strip()
    return p.strip(",;: ")


BIDI_MARKS = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def strip_repeating_lines(pages: list[str], ratio: float = 0.5, edge: int = 3,
                          max_len: int = 80) -> list[str]:
    """
    Remove headers/footers: SHORT lines in the top/bottom `edge` lines of a page that
    repeat on most pages (digits ignored, so "Page 3" matches "Page 4").
    Body text is never touched, and a page is never emptied completely.
    """
    if len(pages) < 3:
        return pages

    def key(line: str) -> str:
        return re.sub(r"\d+", "#", line.strip())

    def edges(lines: list[str]) -> set[int]:
        idx = [i for i, l in enumerate(lines) if l.strip()]
        return {i for i in idx[:edge] + idx[-edge:] if len(lines[i].strip()) <= max_len}

    split = [p.splitlines() for p in pages]
    counts = Counter()
    for lines in split:
        counts.update({key(lines[i]) for i in edges(lines)})
    repeated = {k for k, c in counts.items() if c >= len(pages) * ratio}
    out = []
    for original, lines in zip(pages, split):
        kept = "\n".join(l for i, l in enumerate(lines)
                         if not (i in edges(lines) and key(l) in repeated))
        out.append(kept if kept.strip() or not original.strip() else original)
    return out


def clean_text(text: str, hard_wrapped: bool) -> str:
    """
    hard_wrapped=True  -> PDF text: lines are visual lines, rejoin them into paragraphs.
    hard_wrapped=False -> web text: every non-empty line is already a paragraph.
    Returns paragraphs separated by a blank line.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u00ad", "")  # soft hyphen
    text = BIDI_MARKS.sub("", text)
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if not PAGE_NUMBER.match(l)]
    # RTL PDFs often put a line's final punctuation at the start: ".end of line"
    lines = [LEADING_PUNCT.sub(r"\2\1", l) for l in lines]

    if not hard_wrapped:
        paragraphs = [l for l in lines if l]
    else:
        paragraphs, current = [], ""
        for line in lines:
            if not line:
                # A blank line ends a paragraph only if the sentence ended
                # (otherwise it's a page break in the middle of a sentence).
                if current.endswith(SENTENCE_END):
                    paragraphs.append(current)
                    current = ""
                continue
            if not current:
                current = line
            elif re.search(r"[A-Za-z]-$", current):  # English word split by hyphen
                current = current[:-1] + line
            else:
                current += " " + line
        if current:
            paragraphs.append(current)

    paragraphs = (speakable(p) for p in paragraphs)
    return "\n\n".join(p for p in paragraphs if re.search(r"\w", p))
