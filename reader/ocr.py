"""
OCR with Azure Document Intelligence (prebuilt-read), which supports Hebrew.

Free tier (F0) limits that shape this code:
- 500 pages / month
- only the first 2 pages of a multi-page request are analyzed, max 4 MB per request
  -> we always send ONE page image per request
- 1 analyze request per second
  -> a lock + small delay, one request at a time
"""
import os
import threading
import time

import requests

API_VERSION = "2024-11-30"
MAX_BYTES = 4 * 1024 * 1024
_lock = threading.Lock()


class OCRError(Exception):
    pass


class AzureOCR:
    def __init__(self, endpoint: str, key: str, poll_interval: float = 1.0, timeout: int = 120):
        if not endpoint or not key:
            raise OCRError("OCR is not configured")
        self.url = (f"{endpoint.rstrip('/')}/documentintelligence/documentModels/"
                    f"prebuilt-read:analyze?api-version={API_VERSION}")
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Ocp-Apim-Subscription-Key": key})

    @classmethod
    def from_env(cls) -> "AzureOCR":
        return cls(os.getenv("AZURE_DOCINTEL_ENDPOINT", ""), os.getenv("AZURE_DOCINTEL_KEY", ""))

    def read_image(self, image: bytes) -> str:
        """One page image (JPEG/PNG/TIFF/BMP/HEIF) -> text, paragraphs separated by blank lines."""
        if len(image) > MAX_BYTES:
            raise OCRError("Image is larger than 4 MB")
        with _lock:
            op_url = self._submit(image)
            result = self._poll(op_url)
            time.sleep(self.poll_interval)  # stay under 1 request/second on the free tier
        return _to_text(result)

    def _submit(self, image: bytes) -> str:
        for attempt in range(4):
            r = self.session.post(self.url, data=image, timeout=60,
                                  headers={"Content-Type": "application/octet-stream"})
            if r.status_code == 202:
                return r.headers["Operation-Location"]
            if r.status_code == 429:
                time.sleep(float(r.headers.get("Retry-After", 2 ** attempt)))
                continue
            raise OCRError(f"OCR request failed: {r.status_code} {r.text[:200]}")
        raise OCRError("OCR request failed after retries (rate limit)")

    def _poll(self, op_url: str) -> dict:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            time.sleep(self.poll_interval)
            r = self.session.get(op_url, timeout=30)
            if r.status_code == 429:
                continue
            if r.status_code != 200:
                raise OCRError(f"OCR polling failed: {r.status_code}")
            body = r.json()
            status = body.get("status")
            if status == "succeeded":
                return body.get("analyzeResult", {})
            if status == "failed":
                raise OCRError("OCR failed to read the page")
        raise OCRError("OCR timed out")


def _to_text(result: dict) -> str:
    paragraphs = [p.get("content", "") for p in result.get("paragraphs") or []]
    if not paragraphs:  # fall back to the full content
        paragraphs = (result.get("content") or "").split("\n\n")
    # Lines inside a paragraph are joined with spaces: the voice shouldn't pause mid-sentence.
    cleaned = [" ".join(p.split()) for p in paragraphs]
    return "\n\n".join(p for p in cleaned if p)
