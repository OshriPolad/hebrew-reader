import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

TOKEN_HELP = 'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    app_token: str
    max_pdf_bytes: int = 20 * 1024 * 1024
    max_chars: int = 150_000  # ~1 hour of audio; protects the free TTS quota

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
    return Settings(data_dir=Path(os.getenv("DATA_DIR", "data")), app_token=token)
