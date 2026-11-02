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

## Tests

```bash
python -m pytest
```

## Roadmap
- [x] Phase 1: extraction + cleaning + TTS pipeline (CLI)
- [ ] Phase 2: FastAPI backend + storage
- [ ] Phase 3: Mobile-first RTL web UI
- [ ] Phase 4: Private podcast feed + deployment
- [ ] Phase 5: Testing with the real user

## License
MIT
