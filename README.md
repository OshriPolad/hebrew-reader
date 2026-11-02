# Hebrew Reader

Turns Hebrew or English articles (URLs and PDFs) into natural-sounding audio, read **word for word**: no summarizing, no rewriting.

Built for a real user: a listener who wants articles read aloud while driving or doing chores.

## How it works

```
URL / PDF → extract → clean → split by language → chunk → Azure Neural TTS → MP3
```

| Step | What it does |
|---|---|
| **Extract** | `trafilatura` keeps only article text (no ads/menus). `PyMuPDF` reads PDFs block by block. |
| **Clean** | Rejoins wrapped PDF lines, removes page numbers and repeating headers/footers, fixes RTL punctuation. |
| **Language** | Each paragraph is tagged Hebrew or English, so each is read by a native voice. |
| **TTS** | Azure Neural voices (`he-IL-HilaNeural`, `en-US-AvaNeural`), with pauses between paragraphs. |

### Hebrew-specific problems solved
- `get_text(sort=True)` orders words left-to-right, which **reverses Hebrew sentences**, so it's avoided.
- RTL PDFs put a line's final period at the *start* of the next line (`.סוף המשפט`); this is detected and moved back.
- Page breaks in the middle of a sentence are joined so the voice doesn't pause mid-thought.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate on Mac/Linux)
pip install -r requirements.txt
copy .env.example .env          # then add your Azure Speech key + region
```

## Usage

```bash
python -m reader article.pdf --text-only        # preview the cleaned text (free)
python -m reader https://example.com/article -o article.mp3
```

## Web app (UI)

Hebrew, right-to-left, mobile-first, built for one non-technical listener:
large type and 60px+ touch targets, one screen (add + library), a bottom player with a
96px play button, ±15s skips, speed control, resume-where-you-stopped, and lock-screen controls
(Media Session API). Light and dark mode follow the phone.

```bash
cd frontend
npm install
npm run build        # FastAPI serves frontend/dist at http://127.0.0.1:8000
npm run dev          # or: hot-reload dev server on :5173 (proxies /api to :8000)
```

## API server

```bash
uvicorn app.main:create_app --factory --reload
```
Interactive docs: http://127.0.0.1:8000/docs (click **Authorize** and paste your `APP_TOKEN`).

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/articles/url` | Add an article by link → `202`, processed in background |
| `POST` | `/api/articles/pdf` | Upload a PDF (max 20 MB) → `202` |
| `GET` | `/api/articles` | Library, newest first |
| `GET` | `/api/articles/{id}` | Status: `processing` / `ready` / `failed` |
| `GET` | `/api/articles/{id}/audio` | MP3 stream (supports seeking) |
| `PATCH` | `/api/articles/{id}` | Save listening position / mark as listened |
| `DELETE` | `/api/articles/{id}` | Remove article and audio |

### Security
- **Auth:** bearer token, compared in constant time (`secrets.compare_digest`).
- **SSRF protection:** the server fetches user-supplied links, so every URL *and every redirect hop* is resolved and rejected if it points to a private/internal address (`127.0.0.1`, `10.x`, `169.254.169.254` cloud metadata...).
- **Uploads:** size limit, PDF verified by magic bytes (not file name), server-generated file names (no path traversal), uploaded PDFs deleted after processing.
- **Quota protection:** character limit per article protects the TTS budget.
- **Atomic writes:** audio is written to `.part` then renamed, so a half-generated file is never served.

## Tests

```bash
python -m pytest
```

## Roadmap
- [x] Phase 1: extraction + cleaning + TTS pipeline (CLI)
- [x] Phase 2: FastAPI backend + SQLite storage + background processing
- [x] Phase 3: Mobile-first RTL web UI (React + Vite)
- [ ] Phase 4: Private podcast feed + deployment
- [ ] Phase 5: Testing with the real user

## License
MIT
