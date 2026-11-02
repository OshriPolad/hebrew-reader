"""Extract raw text (and a title) from a URL, raw HTML, or a PDF file."""
from dataclasses import dataclass
from pathlib import Path

import pymupdf
import trafilatura

from .clean import strip_repeating_lines


class ExtractionError(Exception):
    pass


@dataclass
class Extracted:
    text: str
    kind: str  # "url" | "pdf"
    title: str | None


def from_html(html: str | bytes) -> Extracted:
    text = trafilatura.extract(
        html, include_comments=False, include_tables=False, favor_precision=True
    )
    if not text:
        raise ExtractionError("No article text found on the page")
    meta = trafilatura.extract_metadata(html)
    return Extracted(text, "url", meta.title if meta and meta.title else None)


def from_url(url: str) -> Extracted:
    html = trafilatura.fetch_url(url)
    if not html:
        raise ExtractionError(f"Could not download {url}")
    return from_html(html)


def from_pdf(path: str | Path) -> Extracted:
    try:
        doc = pymupdf.open(path)
    except Exception as e:
        raise ExtractionError("The file is not a valid PDF") from e
    with doc:
        # Text blocks ~= paragraphs, so paragraph breaks (and language switches) survive.
        # Don't use sort=True: it orders words left-to-right and reverses Hebrew.
        pages = [
            "\n\n".join(b[4].strip() for b in page.get_text("blocks") if b[6] == 0)
            for page in doc
        ]
    if not any(p.strip() for p in pages):
        raise ExtractionError("PDF has no text layer (scanned?). OCR is not supported yet.")
    return Extracted("\n".join(strip_repeating_lines(pages)), "pdf", Path(path).stem)


def extract(source: str) -> Extracted:
    if source.startswith(("http://", "https://")):
        return from_url(source)
    if source.lower().endswith(".pdf") and Path(source).is_file():
        return from_pdf(source)
    raise ExtractionError(f"Unsupported source: {source}")
