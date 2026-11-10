"""SQLite storage for articles (stdlib only)."""
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id               TEXT PRIMARY KEY,
    title            TEXT NOT NULL,
    source_type      TEXT NOT NULL CHECK (source_type IN ('url', 'file')),
    source           TEXT NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('processing', 'ready', 'failed')),
    error            TEXT,
    char_count       INTEGER,
    duration_seconds REAL,
    position_seconds REAL NOT NULL DEFAULT 0,
    listened         INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage (
    month TEXT PRIMARY KEY,          -- 'YYYY-MM' (UTC)
    chars INTEGER NOT NULL DEFAULT 0, -- billable TTS characters sent this month
    ocr_pages INTEGER NOT NULL DEFAULT 0 -- pages sent to OCR this month
);
"""
UPDATABLE = {"title", "status", "error", "char_count", "duration_seconds",
             "position_seconds", "listened"}


def current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row(r: sqlite3.Row | None) -> dict | None:
    if r is None:
        return None
    d = dict(r)
    d["listened"] = bool(d["listened"])
    return d


class ArticleRepo:
    def __init__(self, path: Path):
        self.path = path
        with self._conn() as c:
            c.executescript(SCHEMA)
            self._migrate(c)

    @staticmethod
    def _migrate(c: sqlite3.Connection) -> None:
        """Upgrade databases created by older versions (keeps all data)."""
        cols = {r["name"] for r in c.execute("PRAGMA table_info(usage)")}
        if "ocr_pages" not in cols:
            c.execute("ALTER TABLE usage ADD COLUMN ocr_pages INTEGER NOT NULL DEFAULT 0")
        sql = c.execute("SELECT sql FROM sqlite_master WHERE name = 'articles'").fetchone()["sql"]
        if "'pdf'" in sql:  # v0.5 and earlier allowed only url/pdf: rebuild with url/file
            c.executescript("""
                ALTER TABLE articles RENAME TO articles_old;
            """ + SCHEMA.split("CREATE TABLE IF NOT EXISTS usage")[0] + """
                INSERT INTO articles SELECT id, title,
                    CASE source_type WHEN 'pdf' THEN 'file' ELSE source_type END,
                    source, status, error, char_count, duration_seconds, position_seconds,
                    listened, created_at, updated_at FROM articles_old;
                DROP TABLE articles_old;
            """)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def create(self, title: str, source_type: str, source: str) -> dict:
        article_id, now = uuid.uuid4().hex, _now()
        with self._conn() as c:
            c.execute(
                "INSERT INTO articles (id, title, source_type, source, status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, 'processing', ?, ?)",
                (article_id, title, source_type, source, now, now),
            )
        return self.get(article_id)

    def get(self, article_id: str) -> dict | None:
        with self._conn() as c:
            return _row(c.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone())

    def list(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM articles ORDER BY created_at DESC, rowid DESC").fetchall()
        return [_row(r) for r in rows]

    def update(self, article_id: str, **fields) -> dict | None:
        bad = set(fields) - UPDATABLE
        if bad:
            raise ValueError(f"Not updatable: {bad}")
        if fields:
            fields["updated_at"] = _now()
            cols = ", ".join(f"{k} = ?" for k in fields)  # keys are whitelisted above
            with self._conn() as c:
                c.execute(f"UPDATE articles SET {cols} WHERE id = ?", (*fields.values(), article_id))
        return self.get(article_id)

    def delete(self, article_id: str) -> bool:
        with self._conn() as c:
            return c.execute("DELETE FROM articles WHERE id = ?", (article_id,)).rowcount > 0

    def fail_interrupted(self) -> int:
        """Jobs still 'processing' at startup were killed by a restart."""
        with self._conn() as c:
            return c.execute(
                "UPDATE articles SET status = 'failed', error = ?, updated_at = ?"
                " WHERE status = 'processing'",
                ("Processing was interrupted. Please add it again.", _now()),
            ).rowcount

    # ---- monthly TTS usage ----
    def add_usage(self, chars: int, month: str | None = None) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO usage (month, chars) VALUES (?, ?)"
                " ON CONFLICT(month) DO UPDATE SET chars = chars + excluded.chars",
                (month or current_month(), chars),
            )

    def get_usage(self, month: str | None = None) -> int:
        with self._conn() as c:
            row = c.execute("SELECT chars FROM usage WHERE month = ?",
                            (month or current_month(),)).fetchone()
        return row["chars"] if row else 0

    def add_ocr_usage(self, pages: int, month: str | None = None) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO usage (month, ocr_pages) VALUES (?, ?)"
                " ON CONFLICT(month) DO UPDATE SET ocr_pages = ocr_pages + excluded.ocr_pages",
                (month or current_month(), pages),
            )

    def get_ocr_usage(self, month: str | None = None) -> int:
        with self._conn() as c:
            row = c.execute("SELECT ocr_pages FROM usage WHERE month = ?",
                            (month or current_month(),)).fetchone()
        return row["ocr_pages"] if row else 0
