import socket

import pymupdf
import pytest
from fastapi.testclient import TestClient

import app.security as security
import app.worker as worker
from app.config import Settings
from app.db import ArticleRepo
from app.main import create_app

TOKEN = "t" * 40
AUTH = {"Authorization": f"Bearer {TOKEN}"}
ARTICLE_HTML = (
    "<html><head><title>כתבה לדוגמה</title></head><body><article><h1>כתבה לדוגמה</h1><p>"
    + "זהו משפט ארוך בעברית שמופיע בכתבה. " * 30
    + "</p></article></body></html>"
).encode()


class FakeTTS:
    calls = []

    def synthesize(self, text, lang):
        FakeTTS.calls.append(lang)
        return b"\xff\xfb" * 6000  # 12 KB ~= 1 second at 96 kbps


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, app_token=TOKEN, max_upload_bytes=1_000_000)


@pytest.fixture
def client(settings, monkeypatch):
    # Pretend every hostname resolves to a public IP (no real DNS in tests)
    real = socket.getaddrinfo

    def fake_getaddrinfo(host, *a, **kw):
        if host in ("news.example", "evil.example"):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        return real(host, *a, **kw)

    monkeypatch.setattr(security.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(worker, "safe_fetch", lambda url, **kw: ARTICLE_HTML)
    FakeTTS.calls = []
    return TestClient(create_app(settings, tts_factory=FakeTTS))


def make_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_htmlbox(pymupdf.Rect(50, 50, 550, 800),
                        "<p dir='rtl'>זהו מסמך לבדיקה. הוא נקרא בקול.</p>")
    return doc.tobytes()


# --- auth ---
def test_health_is_public(client):
    assert client.get("/api/health").json() == {"ok": True}


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}])
def test_requires_token(client, headers):
    assert client.get("/api/articles", headers=headers).status_code == 401


# --- PDF flow ---
def test_pdf_end_to_end(client, settings):
    r = client.post("/api/articles/pdf", headers=AUTH,
                    files={"file": ("מאמר שלי.pdf", make_pdf(), "application/pdf")})
    assert r.status_code == 202 and r.json()["status"] == "processing"
    article_id = r.json()["id"]

    a = client.get(f"/api/articles/{article_id}", headers=AUTH).json()
    assert a["status"] == "ready", a["error"]
    assert a["title"] == "מאמר שלי"
    assert a["duration_seconds"] > 0
    assert not list(settings.upload_dir.iterdir())  # uploaded PDF deleted after processing

    audio = client.get(f"/api/articles/{article_id}/audio?token={TOKEN}")  # <audio src> style
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/mpeg"


def test_rejects_non_pdf(client):
    r = client.post("/api/articles/pdf", headers=AUTH,
                    files={"file": ("fake.pdf", b"MZ not a pdf", "application/pdf")})
    assert r.status_code == 400


def test_rejects_large_pdf(client):
    r = client.post("/api/articles/pdf", headers=AUTH,
                    files={"file": ("big.pdf", b"%PDF" + b"0" * 1_000_001, "application/pdf")})
    assert r.status_code == 413


# --- URL flow ---
def test_url_end_to_end(client):
    r = client.post("/api/articles/url", headers=AUTH, json={"url": "https://news.example/a"})
    assert r.status_code == 202
    a = client.get(f"/api/articles/{r.json()['id']}", headers=AUTH).json()
    assert a["status"] == "ready", a["error"]
    assert a["title"] == "כתבה לדוגמה"
    assert set(FakeTTS.calls) == {"he"}


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/admin", "http://localhost:8000/", "http://10.0.0.5/",
    "http://169.254.169.254/latest/meta-data/", "http://[::1]/",
])
def test_ssrf_blocked(client, url):
    r = client.post("/api/articles/url", headers=AUTH, json={"url": url})
    assert r.status_code == 400


def test_failed_extraction_reports_error(client, monkeypatch):
    monkeypatch.setattr(worker, "safe_fetch", lambda url, **kw: b"<html><body></body></html>")
    r = client.post("/api/articles/url", headers=AUTH, json={"url": "https://news.example/x"})
    a = client.get(f"/api/articles/{r.json()['id']}", headers=AUTH).json()
    assert a["status"] == "failed" and "No article text" in a["error"]


# --- library / progress ---
def test_progress_list_delete(client, settings):
    article_id = client.post("/api/articles/url", headers=AUTH,
                             json={"url": "https://news.example/a"}).json()["id"]
    r = client.patch(f"/api/articles/{article_id}", headers=AUTH,
                     json={"position_seconds": 42.5, "listened": True})
    assert r.json()["position_seconds"] == 42.5 and r.json()["listened"] is True
    assert client.patch(f"/api/articles/{article_id}", headers=AUTH,
                        json={"position_seconds": -1}).status_code == 422

    assert len(client.get("/api/articles", headers=AUTH).json()) == 1
    assert client.delete(f"/api/articles/{article_id}", headers=AUTH).status_code == 204
    assert client.get(f"/api/articles/{article_id}", headers=AUTH).status_code == 404
    assert not (settings.audio_dir / f"{article_id}.mp3").exists()


def test_invalid_id_rejected(client):
    assert client.get("/api/articles/..%2F..%2Fetc", headers=AUTH).status_code in (404, 422)
    assert client.get("/api/articles/not-a-valid-id", headers=AUTH).status_code == 422


def test_interrupted_jobs_marked_failed_on_restart(settings):
    settings.ensure_dirs()
    repo = ArticleRepo(settings.db_path)
    stuck = repo.create("x", "url", "https://news.example")
    assert repo.fail_interrupted() == 1
    assert repo.get(stuck["id"])["status"] == "failed"


# --- safe_fetch redirect protection ---
class FakeResp:
    def __init__(self, location=None, body=b""):
        self.is_redirect = location is not None
        self.headers = {"Location": location} if location else {}
        self.status_code = 302 if location else 200
        self._body = body

    def iter_content(self, n):
        yield self._body

    def close(self):
        pass


def test_redirect_to_internal_address_blocked(client, monkeypatch):
    monkeypatch.setattr(security.requests, "get",
                        lambda url, **kw: FakeResp(location="http://127.0.0.1/secret"))
    with pytest.raises(security.UnsafeURLError):
        security.safe_fetch("https://evil.example/")


def test_safe_fetch_follows_public_redirect(client, monkeypatch):
    responses = iter([FakeResp(location="/real"), FakeResp(body=b"<html>ok</html>")])
    monkeypatch.setattr(security.requests, "get", lambda url, **kw: next(responses))
    assert security.safe_fetch("https://news.example/") == b"<html>ok</html>"
