"""Background job: source -> MP3, updating the article's status."""
import logging
from pathlib import Path

from reader.extract import ExtractionError, from_html, from_pdf
from reader.pipeline import clean, text_to_mp3
from reader.tts import TTSError

from .config import Settings
from .db import ArticleRepo
from .security import UnsafeURLError, safe_fetch

log = logging.getLogger(__name__)
MP3_BYTES_PER_SECOND = 96_000 / 8  # Azure output format is 96 kbps CBR


def _user_message(e: Exception) -> str:
    if isinstance(e, (ExtractionError, UnsafeURLError)):
        return str(e)
    if isinstance(e, TTSError):
        return "The voice service failed. Please try again later."
    return "Something went wrong while processing this article."


def process_article(article_id: str, source_type: str, source: str,
                    repo: ArticleRepo, settings: Settings, tts_factory) -> None:
    part = settings.audio_dir / f"{article_id}.mp3.part"
    try:
        extracted = from_html(safe_fetch(source)) if source_type == "url" else from_pdf(source)
        text = clean(extracted)
        if not text:
            raise ExtractionError("No readable text found")
        if len(text) > settings.max_chars:
            raise ExtractionError(
                f"Article is too long ({len(text):,} characters, max {settings.max_chars:,})")

        text_to_mp3(text, part, tts_factory())
        final = settings.audio_dir / f"{article_id}.mp3"
        part.replace(final)  # atomic: never serve a half-written file

        fields = dict(status="ready", error=None, char_count=len(text),
                      duration_seconds=round(final.stat().st_size / MP3_BYTES_PER_SECOND, 1))
        if source_type == "url" and extracted.title:
            fields["title"] = extracted.title[:200]
        repo.update(article_id, **fields)
    except Exception as e:
        log.exception("Article %s failed", article_id)
        repo.update(article_id, status="failed", error=_user_message(e))
        part.unlink(missing_ok=True)
    finally:
        if source_type == "pdf":
            Path(source).unlink(missing_ok=True)  # don't keep her documents after processing
