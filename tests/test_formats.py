import io
import shutil
import socket
import sqlite3
import subprocess
from pathlib import Path

import pymupdf
import pytest
from docx import Document
from fastapi.testclient import TestClient

import app.security as security
import app.worker as worker
from app.config import Settings
from app.db import ArticleRepo
from app.main import create_app
from reader import ocr as ocr_mod
from reader.extract import ExtractionError, detect_kind, from_docx, from_file, from_pdf

HE = "זהו משפט ארוך בעברית שנכתב לבדיקה של חילוץ טקסט מתוך מסמך. "
TOKEN = "t" * 40
AUTH = {"Authorization": f"Bearer {TOKEN}"}


# ------------------------------------------------------------------ fixtures
class FakeOCR:
    """Stands in for Azure: records calls, returns Hebrew text."""

    def __init__(self):
        self.images, self.reserved = [], []

    def reserve(self, pages):
        self.reserved.append(pages)

    def read_image(self, image):
        self.images.append(image)
        return f"טקסט סרוק מעמוד {len(self.images)}."


def make_docx(paragraphs=(HE * 3, "English paragraph inside the document."), table=True,
              image: bytes | None = None) -> bytes:
    d = Document()
    for p in paragraphs:
        d.add_paragraph(p)
    if table:
        t = d.add_table(rows=1, cols=2)
        t.rows[0].cells[0].text, t.rows[0].cells[1].text = "תא ראשון", "תא שני"
    if image:
        d.add_picture(io.BytesIO(image))
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def text_page_png(text="שורה של טקסט מודפס") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=200)
    page.insert_htmlbox(pymupdf.Rect(20, 20, 380, 180), f"<p dir='rtl'>{text}</p>")
    return page.get_pixmap(dpi=100).tobytes("png")


def make_pdf(pages: list[str]) -> bytes:
    """Each entry: 'text' -> real text page, 'scan' -> image-only page."""
    doc = pymupdf.open()
    for kind in pages:
        page = doc.new_page()
        if kind == "text":
            page.insert_htmlbox(pymupdf.Rect(50, 50, 550, 800), f"<p dir='rtl'>{HE * 4}</p>")
        else:
            page.insert_image(pymupdf.Rect(50, 50, 550, 300), stream=text_page_png())
    return doc.tobytes()


# ------------------------------------------------------------------ detection
def test_detect_kind():
    assert detect_kind(make_pdf(["text"])) == "pdf"
    assert detect_kind(make_docx()) == "docx"
    assert detect_kind(text_page_png()) == "png"
    assert detect_kind(b"\xff\xd8\xff\xe0rest") == "jpeg"
    assert detect_kind(b"{\\rtf1\\ansi hello}") == "rtf"
    assert detect_kind(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 20) == "doc"
    assert detect_kind(b"\0\0\0\x18ftypheic" + b"\0" * 8) == "heif"
    assert detect_kind(b"<html>hello</html>") is None
    assert detect_kind(b"MZ\x90\0 executable") is None


# ------------------------------------------------------------------ Word
def test_docx_paragraphs_and_tables_in_order():
    ex = from_docx(make_docx(), title="מסמך")
    assert ex.kind == "doc" and ex.title == "מסמך"
    parts = ex.text.split("\n\n")
    assert parts[0].startswith("זהו משפט")
    assert parts[1] == "English paragraph inside the document."
    assert parts[2] == "תא ראשון, תא שני"


def test_docx_with_only_a_scanned_image_uses_ocr():
    fake = FakeOCR()
    ex = from_docx(make_docx(paragraphs=(), table=False, image=text_page_png()), fake)
    assert fake.reserved == [1] and len(fake.images) == 1
    assert "טקסט סרוק" in ex.text


def test_docx_with_real_text_does_not_ocr_illustrations():
    fake = FakeOCR()
    from_docx(make_docx(image=text_page_png()), fake)
    assert fake.images == []


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice not installed")
def test_legacy_doc_via_libreoffice(tmp_path):
    src = tmp_path / "old.docx"
    src.write_bytes(make_docx())
    subprocess.run(["soffice", f"-env:UserInstallation=file://{tmp_path}/p", "--headless",
                    "--convert-to", "doc:MS Word 97", "--outdir", str(tmp_path), str(src)],
                   capture_output=True, timeout=120, check=True)
    data = (tmp_path / "old.doc").read_bytes()
    assert detect_kind(data) == "doc"
    ex = from_file(data, title="old")
    assert "זהו משפט ארוך בעברית" in ex.text and "English paragraph" in ex.text


# ------------------------------------------------------------------ PDF
def test_scanned_pdf_without_ocr_explains():
    with pytest.raises(ExtractionError, match="no text layer"):
        from_pdf(make_pdf(["scan", "scan"]))


def test_scanned_pdf_sends_one_image_per_page():
    fake = FakeOCR()
    ex = from_pdf(make_pdf(["scan", "scan", "scan"]), fake, "סריקה")
    assert fake.reserved == [3] and len(fake.images) == 3
    assert all(detect_kind(img) == "jpeg" and len(img) <= 4 * 1024 * 1024 for img in fake.images)
    assert "טקסט סרוק מעמוד 1." in ex.text and "טקסט סרוק מעמוד 3." in ex.text


def test_mixed_pdf_only_ocrs_scanned_pages():
    fake = FakeOCR()
    ex = from_pdf(make_pdf(["text", "scan"]), fake)
    assert len(fake.images) == 1
    assert "זהו משפט ארוך" in ex.text and "טקסט סרוק" in ex.text


def test_image_goes_to_ocr():
    fake = FakeOCR()
    ex = from_file(text_page_png(), "צילום", fake)
    assert ex.kind == "image" and len(fake.images) == 1


def test_unsupported_file():
    with pytest.raises(ExtractionError, match="Unsupported"):
        from_file(b"just some text", "x")


# ------------------------------------------------------------------ API end to end
class FakeTTS:
    def synthesize(self, text, lang):
        return b"\xff\xfb" * 600


class AppOCR:
    calls = 0

    def read_image(self, image):
        AppOCR.calls += 1
        return "כותרת מסמך סרוק. " + "זהו טקסט שזוהה מתוך תמונה. " * 5


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    monkeypatch.setattr(security.socket, "getaddrinfo",
                        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))])
    AppOCR.calls = 0

    def make(ocr=True, **kw):
        s = Settings(data_dir=tmp_path, app_token=TOKEN, **kw)
        return TestClient(create_app(s, tts_factory=FakeTTS, ocr_factory=AppOCR if ocr else None)), s
    return make


def upload(client, name, data):
    r = client.post("/api/articles/file", headers=AUTH, files={"file": (name, data)})
    assert r.status_code == 202, r.text
    return client.get(f"/api/articles/{r.json()['id']}", headers=AUTH).json()


def test_upload_docx(make_client):
    client, _ = make_client()
    a = upload(client, "מכתב_חשוב.docx", make_docx())
    assert a["status"] == "ready", a["error"]
    assert a["title"] == "מכתב חשוב" and a["source_type"] == "file"


def test_upload_photo_counts_ocr_pages(make_client):
    client, _ = make_client()
    a = upload(client, "IMG_0001.png", text_page_png())
    assert a["status"] == "ready", a["error"]
    u = client.get("/api/usage", headers=AUTH).json()
    assert u["ocr_enabled"] and u["ocr_pages_used"] == 1 and u["ocr_pages_quota"] == 500


def test_upload_rejects_unknown_type(make_client):
    client, _ = make_client()
    r = client.post("/api/articles/file", headers=AUTH, files={"file": ("x.pdf", b"not really")})
    assert r.status_code == 400


def test_ocr_monthly_limit_blocks_before_any_call(make_client):
    client, _ = make_client(ocr_monthly_pages=2)
    a = upload(client, "scan.pdf", make_pdf(["scan"] * 3))
    assert a["status"] == "failed" and "Monthly scanning limit" in a["error"]
    assert AppOCR.calls == 0


def test_ocr_page_limit_per_document(make_client):
    client, _ = make_client(max_ocr_pages=2)
    a = upload(client, "scan.pdf", make_pdf(["scan"] * 3))
    assert a["status"] == "failed" and "too long" in a["error"]


def test_scanned_without_ocr_configured(make_client):
    client, _ = make_client(ocr=False)
    a = upload(client, "photo.png", text_page_png())
    assert a["status"] == "failed" and "OCR is not configured" in a["error"]
    assert client.get("/api/usage", headers=AUTH).json()["ocr_enabled"] is False


def test_link_to_a_pdf_file(make_client, monkeypatch):
    client, _ = make_client()
    monkeypatch.setattr(worker, "safe_fetch", lambda url, **kw: make_pdf(["text"]))
    r = client.post("/api/articles/url", headers=AUTH,
                    json={"url": "https://gov.example/files/%D7%97%D7%95%D7%96%D7%A8_2026.pdf"})
    a = client.get(f"/api/articles/{r.json()['id']}", headers=AUTH).json()
    assert a["status"] == "ready", a["error"]
    assert a["title"] == "חוזר 2026"


def test_link_to_an_image_uses_ocr(make_client, monkeypatch):
    client, _ = make_client()
    monkeypatch.setattr(worker, "safe_fetch", lambda url, **kw: text_page_png())
    r = client.post("/api/articles/url", headers=AUTH, json={"url": "https://x.example/scan.png"})
    a = client.get(f"/api/articles/{r.json()['id']}", headers=AUTH).json()
    assert a["status"] == "ready" and AppOCR.calls == 1


def test_old_pdf_endpoint_still_works(make_client):
    client, _ = make_client()
    r = client.post("/api/articles/pdf", headers=AUTH, files={"file": ("a.pdf", make_pdf(["text"]))})
    assert r.status_code == 202


# ------------------------------------------------------------------ DB migration
def test_migrates_v05_database(tmp_path):
    db = tmp_path / "app.db"
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE articles (id TEXT PRIMARY KEY, title TEXT NOT NULL,
          source_type TEXT NOT NULL CHECK (source_type IN ('url', 'pdf')), source TEXT NOT NULL,
          status TEXT NOT NULL CHECK (status IN ('processing', 'ready', 'failed')), error TEXT,
          char_count INTEGER, duration_seconds REAL, position_seconds REAL NOT NULL DEFAULT 0,
          listened INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE usage (month TEXT PRIMARY KEY, chars INTEGER NOT NULL DEFAULT 0);
        INSERT INTO articles VALUES ('a1','old pdf','pdf','x','ready',NULL,10,60,12,0,'t','t');
        INSERT INTO usage VALUES ('2026-11', 1234);
    """)
    c.commit()
    c.close()
    repo = ArticleRepo(db)
    a = repo.get("a1")
    assert a["source_type"] == "file" and a["position_seconds"] == 12
    assert repo.get_usage("2026-11") == 1234 and repo.get_ocr_usage("2026-11") == 0
    repo.create("new", "file", "y")  # new constraint accepts 'file'


# ------------------------------------------------------------------ Azure OCR client
class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers, self.text = status, body, headers or {}, ""

    def json(self):
        return self._body


def test_azure_ocr_submit_poll_and_paragraphs(monkeypatch):
    monkeypatch.setattr(ocr_mod.time, "sleep", lambda s: None)
    client = ocr_mod.AzureOCR("https://x.cognitiveservices.azure.com/", "k")
    posts = iter([Resp(429, headers={"Retry-After": "0"}),
                  Resp(202, headers={"Operation-Location": "https://op/1"})])
    gets = iter([Resp(200, {"status": "running"}),
                 Resp(200, {"status": "succeeded", "analyzeResult": {"paragraphs": [
                     {"content": "שורה ראשונה\nממשיכה כאן."}, {"content": "פסקה שנייה."}]}})])
    monkeypatch.setattr(client.session, "post", lambda *a, **k: next(posts))
    monkeypatch.setattr(client.session, "get", lambda *a, **k: next(gets))
    assert client.read_image(b"img") == "שורה ראשונה ממשיכה כאן.\n\nפסקה שנייה."
    assert "prebuilt-read:analyze" in client.url


def test_azure_ocr_requires_config():
    with pytest.raises(ocr_mod.OCRError):
        ocr_mod.AzureOCR("", "")
