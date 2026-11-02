from reader.tts import build_ssml


def test_ssml_escapes_and_adds_pauses():
    ssml = build_ssml("A & B\n\nC < D", "en", "en-US-AvaNeural")
    assert "A &amp; B" in ssml and "C &lt; D" in ssml
    assert '<break time="600ms"/>' in ssml
    assert "xml:lang='en-US'" in ssml
