import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

TOKEN_HELP = 'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    app_token: str
    feed_token: str = ""  # empty -> podcast feed disabled
    public_url: str = ""  # e.g. https://reader.duckdns.org (used for links inside the feed)
    max_pdf_bytes: int = 20 * 1024 * 1024
    max_chars: int = 60_000  # per article (~10,000 words, ~1 hour of audio)
    monthly_quota: int = 500_000  # Azure F0 free tier: 0.5M characters / month

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.audio_dir, self.upload_dir):
            d.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    load_dotenv()
    token = os.getenv("APP_TOKEN", "")
    if len(token) < 32:
        raise RuntimeError(f"APP_TOKEN must be set in .env (32+ chars). {TOKEN_HELP}")
    feed_token = os.getenv("FEED_TOKEN", "")
    if feed_token and (len(feed_token) < 32 or feed_token == token):
        raise RuntimeError(f"FEED_TOKEN must be 32+ chars and different from APP_TOKEN. {TOKEN_HELP}")
    return Settings(
        data_dir=Path(os.getenv("DATA_DIR", "data")),
        app_token=token,
        feed_token=feed_token,
        public_url=os.getenv("PUBLIC_URL", "").rstrip("/"),
        max_chars=int(os.getenv("MAX_CHARS", "60000")),
        monthly_quota=int(os.getenv("MONTHLY_CHAR_QUOTA", "500000")),
    )
