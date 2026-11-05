import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import ArticleRepo
from app.main import create_app

APP_TOKEN, FEED_TOKEN = "a" * 40, "f" * 40


@pytest.fixture
def setup(tmp_path):
    s = Settings(data_dir=tmp_path, app_token=APP_TOKEN, feed_token=FEED_TOKEN,
                 public_url="https://reader.example")
    client = TestClient(create_app(s, tts_factory=lambda: None))
    repo = ArticleRepo(s.db_path)
    ready = repo.create("כתבה & מבחן <1>", "url", "x")
    repo.update(ready["id"], status="ready", duration_seconds=125.4)
    (s.audio_dir / f"{ready['id']}.mp3").write_bytes(b"\xff\xfb" * 100)
    repo.create("עדיין בהכנה", "url", "y")  # processing -> not in feed
    return client, ready["id"]


def test_feed_lists_ready_episodes(setup):
    client, article_id = setup
    r = client.get(f"/feed/{FEED_TOKEN}/podcast.xml")
    assert r.status_code == 200 and "rss" in r.headers["content-type"]
    root = ET.fromstring(r.content)  # also proves the XML is valid (escaping works)
    items = root.findall("./channel/item")
    assert len(items) == 1
    assert items[0].find("title").text == "כתבה & מבחן <1>"
    enc = items[0].find("enclosure")
    assert enc.get("url") == f"https://reader.example/feed/{FEED_TOKEN}/audio/{article_id}.mp3"
    assert enc.get("length") == "200" and enc.get("type") == "audio/mpeg"


def test_feed_audio(setup):
    client, article_id = setup
    r = client.get(f"/feed/{FEED_TOKEN}/audio/{article_id}.mp3")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg"


@pytest.mark.parametrize("token", ["wrong", APP_TOKEN])
def test_wrong_token_is_404(setup, token):
    client, article_id = setup
    assert client.get(f"/feed/{token}/podcast.xml").status_code == 404
    assert client.get(f"/feed/{token}/audio/{article_id}.mp3").status_code == 404


def test_feed_token_cannot_use_api(setup):
    client, _ = setup
    r = client.get("/api/articles", headers={"Authorization": f"Bearer {FEED_TOKEN}"})
    assert r.status_code == 401


def test_feed_disabled_without_token(tmp_path):
    client = TestClient(create_app(Settings(data_dir=tmp_path, app_token=APP_TOKEN)))
    assert client.get(f"/feed/{FEED_TOKEN}/podcast.xml").status_code == 404
