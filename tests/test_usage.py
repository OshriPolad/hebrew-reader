import socket

import pytest
from fastapi.testclient import TestClient

import app.security as security
import app.worker as worker
from app.config import Settings
from app.db import ArticleRepo
from app.main import create_app
from reader.tts import billable_chars

TOKEN = "t" * 40
AUTH = {"Authorization": f"Bearer {TOKEN}"}
PARA = "זהו משפט ארוך בעברית שמופיע בכתבה. " * 30
HTML = f"<html><head><title>כתבה</title></head><body><article><p>{PARA}</p></article></body></html>".encode()


class FakeTTS:
    calls = 0

    def synthesize(self, text, lang):
        FakeTTS.calls += 1
        return b"\xff\xfb" * 600


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    monkeypatch.setattr(security.socket, "getaddrinfo",
                        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))])
    monkeypatch.setattr(worker, "safe_fetch", lambda url, **kw: HTML)
    FakeTTS.calls = 0

    def make(**kw):
        s = Settings(data_dir=tmp_path, app_token=TOKEN, **kw)
        return TestClient(create_app(s, tts_factory=FakeTTS)), s
    return make


def add(client):
    r = client.post("/api/articles/url", headers=AUTH, json={"url": "https://news.example/a"})
    return client.get(f"/api/articles/{r.json()['id']}", headers=AUTH).json()


def test_billable_counts_breaks_but_not_speak_voice():
    assert billable_chars("אבג") == 3
    assert billable_chars("א\n\nב") == 2 + len('<break time="600ms"/>')
    assert billable_chars("A & B") == len("A &amp; B")


def test_usage_tracked_after_processing(make_client):
    client, _ = make_client()
    assert client.get("/api/usage", headers=AUTH).json()["used_chars"] == 0
    a = add(client)
    assert a["status"] == "ready"
    u = client.get("/api/usage", headers=AUTH).json()
    assert u["used_chars"] == a["char_count"] > 0
    assert u["remaining_chars"] == u["quota_chars"] - u["used_chars"]


def test_quota_exceeded_blocks_before_any_tts_call(make_client):
    client, s = make_client(monthly_quota=100)
    a = add(client)
    assert a["status"] == "failed" and "Monthly reading limit" in a["error"]
    assert FakeTTS.calls == 0  # nothing spent


def test_quota_counts_only_this_month(make_client):
    client, s = make_client(monthly_quota=50_000)
    ArticleRepo(s.db_path).add_usage(49_999, month="1999-01")  # old month: ignored
    assert add(client)["status"] == "ready"


def test_max_chars_per_article(make_client):
    client, _ = make_client(max_chars=100)
    a = add(client)
    assert a["status"] == "failed" and "too long" in a["error"]
