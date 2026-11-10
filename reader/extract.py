"""
Extract raw text (and a title) from web pages, PDFs (text or scanned), Word documents
(.docx, and .doc/.rtf/.odt via LibreOffice) and images (via OCR).

`ocr` is any object with:
    reserve(pages: int)        -> raises if the pages can't be OCR'd (budget, limits, not configured)
    read_image(image: bytes)   -> str
"""
import io
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pymupdf
import trafilatura

from .clean import strip_repeating_lines

SCANNED_PAGE_MIN_CHARS = 25     # a PDF page with less real text than this is treated as scanned
SCANNED_DOC_MIN_CHARS = 200     # a Word file with less text than this (but images) is a scan
OCR_MAX_BYTES = 4 * 1024 * 1024  # Azure free tier limit per request
IMAGE_KINDS = {"jpeg", "png", "tiff", "bmp", "heif"}
LEGACY_OFFICE = {"doc", "rtf", "odt"}


class ExtractionError(Exception):
    pass


@dataclass
class Extracted:
    text: str
    kind: str  # "url" | "pdf" | "doc" | "image"  (pdf text is hard-wrapped, the rest isn't)
    title: str | None


# ---------------------------------------------------------------- file type detection
def detect_kind(data: bytes) -> str | None:
    """Identify a file by its content (magic bytes), never by its name."""
    if data[:4] == b"%PDF":
        return "pdf"
    if data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = set(z.namelist())
                if "word/document.xml" in names:
                    return "docx"
                if "mimetype" in names and z.read("mimetype").startswith(
                        b"application/vnd.oasis.opendocument.text"):
                    return "odt"
        except zipfile.BadZipFile:
            return None
        return None
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "doc"  # OLE2 container (Word 97-2003)
    if data[:5] == b"{\\rtf":
        return "rtf"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if data[:2] == b"BM":
        return "bmp"
    if data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"heim", b"heis"):
        return "heif"  # iPhone photos
    return None


def _need_ocr(ocr, pages: int):
    if ocr is None:
        raise ExtractionError("This document is scanned, and OCR is not configured on the server")
    ocr.reserve(pages)
    return ocr


# ---------------------------------------------------------------- web pages
def from_html(html: str | bytes) -> Extracted:
    text = trafilatura.extract(
        html, include_comments=False, include_tables=False, favor_precision=True
    )
    if not text:
        raise ExtractionError("No article text found on the page")
    meta = trafilatura.extract_metadata(html)
    return Extracted(text, "url", meta.title if meta and meta.title else None)


def from_url(url: str) -> Extracted:
    html = trafilatura.fetch_url(url)
    if not html:
        raise ExtractionError(f"Could not download {url}")
    return from_html(html)


# ---------------------------------------------------------------- PDF
def _page_text(page) -> str:
    # Text blocks ~= paragraphs, so paragraph breaks (and language switches) survive.
    # Don't use sort=True: it orders words left-to-right and reverses Hebrew.
    return "\n\n".join(b[4].strip() for b in page.get_text("blocks") if b[6] == 0)


def _render_page(page) -> bytes:
    """Page -> grayscale JPEG under the OCR size limit."""
    for dpi in (200, 150, 110):
        img = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY).tobytes("jpeg", jpg_quality=85)
        if len(img) <= OCR_MAX_BYTES:
            return img
    raise ExtractionError("A scanned page is too large to read")


def from_pdf(source: bytes | str | Path, ocr=None, title: str | None = None) -> Extracted:
    try:
        doc = (pymupdf.open(stream=source, filetype="pdf") if isinstance(source, bytes)
               else pymupdf.open(source))
    except Exception as e:
        raise ExtractionError("The file is not a valid PDF") from e
    with doc:
        texts = [_page_text(page) for page in doc]
        scanned = [i for i, page in enumerate(doc)
                   if len(texts[i].strip()) < SCANNED_PAGE_MIN_CHARS and page.get_images()]
        if scanned:
            if ocr is None and not any(t.strip() for t in texts):
                raise ExtractionError(
                    "PDF has no text layer (scanned?) and OCR is not configured on the server")
            if ocr is not None:
                _need_ocr(ocr, len(scanned))
                for i in scanned:  # only the scanned pages: mixed PDFs keep their real text
                    texts[i] = ocr.read_image(_render_page(doc[i]))
    if not any(t.strip() for t in texts):
        raise ExtractionError("No readable text found in the document")
    if title is None and not isinstance(source, bytes):
        title = Path(source).stem
    return Extracted("\n".join(strip_repeating_lines(texts)), "pdf", title)


# ---------------------------------------------------------------- Word
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A_BLIP = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
R_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"


def _xml_text(el) -> str:
    parts = []
    for node in el.iter():
        if node.tag == W + "t":
            parts.append(node.text or "")
        elif node.tag in (W + "tab", W + "br", W + "cr"):
            parts.append(" ")
    return " ".join("".join(parts).split())


def from_docx(data: bytes, ocr=None, title: str | None = None) -> Extracted:
    from docx import Document  # imported lazily: only needed for Word files

    try:
        doc = Document(io.BytesIO(data))
    except Exception as e:
        raise ExtractionError("Could not open this Word file") from e

    paragraphs, image_ids = [], []
    for child in doc.element.body.iterchildren():
        if child.tag == W + "p":
            if text := _xml_text(child):
                paragraphs.append(text)
            image_ids += [b.get(R_EMBED) for b in child.iter(A_BLIP) if b.get(R_EMBED)]
        elif child.tag == W + "tbl":
            for row in child.iter(W + "tr"):
                cells = [t for tc in row.iter(W + "tc") if (t := _xml_text(tc))]
                if cells:
                    paragraphs.append(", ".join(cells))  # comma = short pause between cells

    text_chars = sum(len(p) for p in paragraphs)
    if text_chars < SCANNED_DOC_MIN_CHARS and image_ids:
        # A Word file that is basically pasted scans: read the images in document order.
        blobs = [doc.part.related_parts[rid].blob for rid in image_ids
                 if rid in doc.part.related_parts]
        blobs = [b for b in blobs if detect_kind(b) in IMAGE_KINDS]
        if blobs:
            _need_ocr(ocr, len(blobs))
            paragraphs += [ocr.read_image(_fit_for_ocr(b)) for b in blobs]

    paragraphs = [p for p in paragraphs if p.strip()]
    if not paragraphs:
        raise ExtractionError("No readable text found in the document")
    doc_title = (doc.core_properties.title or "").strip()
    return Extracted("\n\n".join(paragraphs), "doc", doc_title or title)


def _convert_to_docx(data: bytes, kind: str) -> bytes:
    """Old .doc (and .rtf/.odt) -> .docx with headless LibreOffice."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise ExtractionError("Old Word files (.doc) are not supported on this server")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"input.{kind}"
        src.write_bytes(data)
        cmd = [soffice, f"-env:UserInstallation=file://{tmp}/profile", "--headless",
               "--norestore", "--nolockcheck", "--convert-to", "docx:MS Word 2007 XML",
               "--outdir", tmp, str(src)]
        try:
            subprocess.run(cmd, capture_output=True, timeout=120, check=False)
        except subprocess.TimeoutExpired as e:
            raise ExtractionError("Converting the Word file took too long") from e
        out = Path(tmp) / "input.docx"
        if not out.exists():
            raise ExtractionError("Could not open this Word file")
        return out.read_bytes()


# ---------------------------------------------------------------- images
def _fit_for_ocr(image: bytes) -> bytes:
    """Shrink an image until it fits the OCR size limit (HEIF is sent as-is)."""
    if len(image) <= OCR_MAX_BYTES or detect_kind(image) == "heif":
        return image
    pix = pymupdf.Pixmap(image)
    if pix.alpha:
        pix = pymupdf.Pixmap(pix, 0)
    out = pix.tobytes("jpeg", jpg_quality=85)
    while len(out) > OCR_MAX_BYTES and pix.width > 600:
        pix.shrink(1)  # halve width and height
        out = pix.tobytes("jpeg", jpg_quality=85)
    return out


def from_image(data: bytes, ocr=None, title: str | None = None) -> Extracted:
    _need_ocr(ocr, 1)
    text = ocr.read_image(_fit_for_ocr(data))
    if not text.strip():
        raise ExtractionError("No readable text found in the image")
    return Extracted(text, "image", title)


# ---------------------------------------------------------------- dispatch
def from_file(data: bytes, title: str | None = None, ocr=None) -> Extracted:
    kind = detect_kind(data)
    if kind == "pdf":
        return from_pdf(data, ocr, title)
    if kind == "docx":
        return from_docx(data, ocr, title)
    if kind in LEGACY_OFFICE:
        return from_docx(_convert_to_docx(data, kind), ocr, title)
    if kind in IMAGE_KINDS:
        return from_image(data, ocr, title)
    raise ExtractionError("Unsupported file type")


def extract(source: str, ocr=None) -> Extracted:
    """CLI helper: a URL (web page) or a local file of any supported type."""
    if source.startswith(("http://", "https://")):
        return from_url(source)
    path = Path(source)
    if path.is_file():
        return from_file(path.read_bytes(), path.stem, ocr)
    raise ExtractionError(f"Unsupported source: {source}")
