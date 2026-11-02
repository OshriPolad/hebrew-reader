"""Azure Neural TTS over the REST API (no SDK needed)."""
import os
import time
from xml.sax.saxutils import escape

import requests

DEFAULT_VOICES = {"he": "he-IL-HilaNeural", "en": "en-US-AvaNeural"}
LOCALES = {"he": "he-IL", "en": "en-US"}
PARAGRAPH_PAUSE = '<break time="600ms"/>'


class TTSError(Exception):
    pass


def build_ssml(text: str, lang: str, voice: str) -> str:
    body = PARAGRAPH_PAUSE.join(escape(p) for p in text.split("\n\n") if p.strip())
    return (
        f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' "
        f"xml:lang='{LOCALES[lang]}'><voice name='{voice}'>{body}</voice></speak>"
    )


class AzureTTS:
    def __init__(self, key: str, region: str, voices: dict[str, str] | None = None):
        if not key or not region:
            raise TTSError("AZURE_SPEECH_KEY and AZURE_SPEECH_REGION must be set in .env")
        self.url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
        self.voices = voices or DEFAULT_VOICES
        self.session = requests.Session()
        self.session.headers.update({
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
            "User-Agent": "hebrew-reader",
        })

    @classmethod
    def from_env(cls) -> "AzureTTS":
        return cls(
            os.getenv("AZURE_SPEECH_KEY", ""),
            os.getenv("AZURE_SPEECH_REGION", ""),
            {"he": os.getenv("VOICE_HE", DEFAULT_VOICES["he"]),
             "en": os.getenv("VOICE_EN", DEFAULT_VOICES["en"])},
        )

    def synthesize(self, text: str, lang: str) -> bytes:
        ssml = build_ssml(text, lang, self.voices[lang]).encode("utf-8")
        for attempt in range(3):
            r = self.session.post(self.url, data=ssml, timeout=90)
            if r.status_code == 200:
                return r.content
            if r.status_code in (429, 500, 502, 503):
                time.sleep(2 ** attempt)
                continue
            raise TTSError(f"Azure TTS failed: {r.status_code} {r.text[:200]}")
        raise TTSError("Azure TTS failed after 3 retries")
