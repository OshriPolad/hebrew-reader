"""Background job: source -> MP3, updating the article's status."""
import logging
import threading
from pathlib import Path
from urllib.parse import unquote, urlparse

from reader.extract import ExtractionError, detect_kind, from_file, from_html
from reader.ocr import OCRError
from reader.pipeline import clean, plan, text_to_mp3
from reader.tts import TTSError, billable_chars

from .config import Settings
from .db import ArticleRepo
from .security import UnsafeURLError, safe_fetch

log = logging.getLogger(__name__)
MP3_BYTES_PER_SECOND = 96_000 / 8  # Azure output format is 96 kbps CBR

# The free tier allows ~1 concurrent request: synthesize one article at a time.
# (Fetching/cleaning still runs in parallel; only the TTS part waits.)
_tts_lock = threading.Lock()


class QuotaExceeded(Exception):
    pass


class BudgetedOCR:
    """Wraps the OCR client with the monthly page budget and per-document limit."""

    def __init__(self, ocr_factory, repo: ArticleRepo, settings: Settings):
        self._factory, self._repo, self._settings = ocr_factory, repo, settings
        self._client = None

    def reserve(self, pages: int) -> None:
        s = self._settings
        if self._factory is None:
            raise ExtractionError("This document is scanned, and OCR is not configured on the server")
        if pages > s.max_ocr_pages:
            raise ExtractionError(
                f"Scanned document is too long ({pages} pages, max {s.max_ocr_pages})")
        if self._repo.get_ocr_usage() + pages > s.ocr_monthly_pages:
            raise QuotaExceeded("Monthly scanning limit reached")

    def read_image(self, image: bytes) -> str:
        if self._client is None:
            self._client = self._factory()
        text = self._client.read_image(image)
        self._repo.add_ocr_usage(1)  # counted only after a successful (= billed) page
        return text


def _user_message(e: Exception) -> str:
    if isinstance(e, (ExtractionError, UnsafeURLError, QuotaExceeded)):
        return str(e)
    if isinstance(e, OCRError):
        return "The scanning service failed. Please try again later."
    if isinstance(e, TTSError):
        return "The voice service failed. Please try again later."
    return "Something went wrong while processing this article."


def _title_from_url(url: str) -> str:
    name = unquote(Path(urlparse(url).path).stem).replace("_", " ").strip()
    return name or urlparse(url).hostname or "document"


def process_article(article_id: str, source_type: str, source: str,
                    repo: ArticleRepo, settings: Settings, tts_factory,
                    ocr_factory=None, title_hint: str | None = None) -> None:
    part = settings.audio_dir / f"{article_id}.mp3.part"
    ocr = BudgetedOCR(ocr_factory, repo, settings)
    try:
        if source_type == "url":
            body = safe_fetch(source, max_bytes=settings.max_upload_bytes)
            # A link can point to a web page *or* straight to a PDF / Word file / image.
            extracted = (from_file(body, _title_from_url(source), ocr) if detect_kind(body)
                         else from_html(body))
        else:
            extracted = from_file(Path(source).read_bytes(), title_hint, ocr)

        text = clean(extracted)
        if not text:
            raise ExtractionError("No readable text found")
        if len(text) > settings.max_chars:
            raise ExtractionError(
                f"Article is too long ({len(text):,} characters, max {settings.max_chars:,})")

        cost = sum(billable_chars(c) for _, c in plan(text))
        with _tts_lock:
            # Check before spending anything: never burn quota on half an article.
            if repo.get_usage() + cost > settings.monthly_quota:
                raise QuotaExceeded("Monthly reading limit reached")
            text_to_mp3(text, part, tts_factory(),
                        on_chunk_done=lambda c: repo.add_usage(billable_chars(c)))

        final = settings.audio_dir / f"{article_id}.mp3"
        part.replace(final)  # atomic: never serve a half-written file

        fields = dict(status="ready", error=None, char_count=cost,
                      duration_seconds=round(final.stat().st_size / MP3_BYTES_PER_SECOND, 1))
        if source_type == "url" and extracted.title:
            fields["title"] = extracted.title[:200]
        repo.update(article_id, **fields)
    except Exception as e:
        log.exception("Article %s failed", article_id)
        repo.update(article_id, status="failed", error=_user_message(e))
        part.unlink(missing_ok=True)
    finally:
        if source_type == "file":
            Path(source).unlink(missing_ok=True)  # don't keep her documents after processing
