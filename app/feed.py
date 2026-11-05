"""
Private podcast feed: every ready article becomes an episode.
Subscribe once in a podcast app (Apple Podcasts / Pocket Casts / AntennaPod) via
  https://<domain>/feed/<FEED_TOKEN>/podcast.xml
The feed token is separate from APP_TOKEN: it can only *read* audio, never add or delete.
"""
import secrets
from datetime import datetime
from email.utils import format_datetime
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Request
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, Response

from .config import Settings
from .db import ArticleRepo


def build_rss(articles: list[dict], base: str, token: str, settings: Settings) -> str:
    items = []
    for a in articles:
        if a["status"] != "ready":
            continue
        path = settings.audio_dir / f"{a['id']}.mp3"
        if not path.exists():
            continue
        url = f"{base}/feed/{token}/audio/{a['id']}.mp3"
        items.append(f"""
    <item>
      <title>{escape(a['title'])}</title>
      <guid isPermaLink="false">{a['id']}</guid>
      <pubDate>{format_datetime(datetime.fromisoformat(a['created_at']))}</pubDate>
      <enclosure url="{escape(url)}" length="{path.stat().st_size}" type="audio/mpeg"/>
      <itunes:duration>{int(a['duration_seconds'] or 0)}</itunes:duration>
    </item>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>ההקראות שלי</title>
    <link>{escape(base)}</link>
    <description>כתבות ומסמכים, מוקראים מילה במילה.</description>
    <language>he</language>
    <itunes:author>Hebrew Reader</itunes:author>
    <itunes:explicit>false</itunes:explicit>
    <itunes:block>Yes</itunes:block>{''.join(items)}
  </channel>
</rss>
"""


def make_feed_router(settings: Settings, repo: ArticleRepo) -> APIRouter:
    router = APIRouter(prefix="/feed", include_in_schema=False)
    expected = settings.feed_token.encode()

    def check(token: str) -> None:
        # 404 (not 401) so a wrong token doesn't even reveal the feed exists
        if not secrets.compare_digest(token.encode(), expected):
            raise HTTPException(404)

    @router.get("/{token}/podcast.xml")
    def podcast(request: Request, token: str):
        check(token)
        base = settings.public_url or str(request.base_url).rstrip("/")
        xml = build_rss(repo.list(), base, token, settings)
        return Response(xml, media_type="application/rss+xml; charset=utf-8")

    @router.get("/{token}/audio/{article_id}.mp3")
    def audio(token: str, article_id: str = PathParam(pattern=r"^[0-9a-f]{32}$")):
        check(token)
        path = settings.audio_dir / f"{article_id}.mp3"
        if not path.exists():
            raise HTTPException(404)
        return FileResponse(path, media_type="audio/mpeg")

    return router
