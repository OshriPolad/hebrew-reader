"""Extract raw text from a URL or a PDF file."""
from pathlib import Path

import pymupdf
import trafilatura

from .clean import strip_repeating_lines


class ExtractionError(Exception):
    pass


def from_url(url: str) -> str:
    html = trafilatura.fetch_url(url)
    if not html:
        raise ExtractionError(f"Could not download {url}")
    text = trafilatura.extract(
        html, include_comments=False, include_tables=False, favor_precision=True
    )
    if not text:
        raise ExtractionError("No article text found on the page")
    return text


def from_pdf(path: str | Path) -> str:
    with pymupdf.open(path) as doc:
        # Text blocks ~= paragraphs, so paragraph breaks (and language switches) survive.
        # Don't use sort=True: it orders words left-to-right and reverses Hebrew.
        pages = [
            "\n\n".join(b[4].strip() for b in page.get_text("blocks") if b[6] == 0)
            for page in doc
        ]
    if not any(p.strip() for p in pages):
        raise ExtractionError("PDF has no text layer (scanned?). OCR is not supported yet.")
    return "\n".join(strip_repeating_lines(pages))


def extract(source: str) -> tuple[str, str]:
    """Return (raw_text, kind) where kind is 'url' or 'pdf'."""
    if source.startswith(("http://", "https://")):
        return from_url(source), "url"
    if source.lower().endswith(".pdf") and Path(source).is_file():
        return from_pdf(source), "pdf"
    raise ExtractionError(f"Unsupported source: {source}")
