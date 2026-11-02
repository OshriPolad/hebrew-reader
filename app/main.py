"""
Hebrew Reader API.
Run:  uvicorn app.main:create_app --factory --reload
Docs: http://127.0.0.1:8000/docs
"""
import logging
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import (APIRouter, BackgroundTasks, Depends, FastAPI, File, HTTPException,
                     UploadFile)
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl

from reader.tts import AzureTTS

from .config import Settings, load_settings
from .db import ArticleRepo
from .security import UnsafeURLError, make_auth, validate_public_url
from .worker import process_article

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
ArticleId = PathParam(pattern=r"^[0-9a-f]{32}$")


class UrlIn(BaseModel):
    url: HttpUrl


class ProgressIn(BaseModel):
    position_seconds: float | None = Field(default=None, ge=0)
    listened: bool | None = None


class ArticleOut(BaseModel):
    id: str
    title: str
    source_type: Literal["url", "pdf"]
    status: Literal["processing", "ready", "failed"]
    error: str | None
    char_count: int | None
    duration_seconds: float | None
    position_seconds: float
    listened: bool
    created_at: str
    updated_at: str


def create_app(settings: Settings | None = None, tts_factory=None) -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    settings = settings or load_settings()
    settings.ensure_dirs()
    repo = ArticleRepo(settings.db_path)
    repo.fail_interrupted()
    tts_factory = tts_factory or AzureTTS.from_env

    app = FastAPI(title="Hebrew Reader API", version="0.2.0")
    api = APIRouter(prefix="/api", dependencies=[Depends(make_auth(settings.app_token))])

    def get_or_404(article_id: str) -> dict:
        article = repo.get(article_id)
        if not article:
            raise HTTPException(404, "Article not found")
        return article

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @api.post("/articles/url", status_code=202, response_model=ArticleOut)
    def add_url(body: UrlIn, background: BackgroundTasks):
        url = str(body.url)
        try:
            validate_public_url(url)
        except UnsafeURLError as e:
            raise HTTPException(400, str(e))
        article = repo.create(title=urlparse(url).hostname or url, source_type="url", source=url)
        background.add_task(process_article, article["id"], "url", url, repo, settings, tts_factory)
        return article

    @api.post("/articles/pdf", status_code=202, response_model=ArticleOut)
    async def add_pdf(background: BackgroundTasks, file: UploadFile = File(...)):
        data = await file.read(settings.max_pdf_bytes + 1)
        if len(data) > settings.max_pdf_bytes:
            raise HTTPException(413, f"PDF is larger than {settings.max_pdf_bytes // 2**20} MB")
        if not data.startswith(b"%PDF"):  # check the content, not the file name
            raise HTTPException(400, "File is not a PDF")
        title = Path(file.filename or "document").stem.replace("_", " ").strip()[:200] or "document"
        article = repo.create(title=title, source_type="pdf", source=title)
        path = settings.upload_dir / f"{article['id']}.pdf"  # server-chosen name: no path traversal
        path.write_bytes(data)
        background.add_task(process_article, article["id"], "pdf", str(path), repo, settings,
                            tts_factory)
        return article

    @api.get("/articles", response_model=list[ArticleOut])
    def list_articles():
        return repo.list()

    @api.get("/articles/{article_id}", response_model=ArticleOut)
    def get_article(article_id: str = ArticleId):
        return get_or_404(article_id)

    @api.get("/articles/{article_id}/audio")
    def get_audio(article_id: str = ArticleId):
        article = get_or_404(article_id)
        path = settings.audio_dir / f"{article_id}.mp3"
        if article["status"] != "ready" or not path.exists():
            raise HTTPException(409, "Audio is not ready")
        return FileResponse(path, media_type="audio/mpeg")  # supports Range -> seeking works

    @api.patch("/articles/{article_id}", response_model=ArticleOut)
    def update_progress(body: ProgressIn, article_id: str = ArticleId):
        get_or_404(article_id)
        return repo.update(article_id, **body.model_dump(exclude_none=True))

    @api.delete("/articles/{article_id}", status_code=204)
    def delete_article(article_id: str = ArticleId):
        get_or_404(article_id)
        repo.delete(article_id)
        (settings.audio_dir / f"{article_id}.mp3").unlink(missing_ok=True)
        return Response(status_code=204)

    app.include_router(api)
    # Serve the built UI (npm run build) from the same server: one URL, no CORS.
    if FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="ui")
    return app
