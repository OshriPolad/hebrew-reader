from reader.lang import chunk, detect, segment_by_language


def test_detect():
    assert detect("שלום עולם") == "he"
    assert detect("Hello world") == "en"
    assert detect("123 - 456") is None


def test_segments_merge_same_language():
    text = "פסקה א.\n\nפסקה ב.\n\nEnglish part.\n\n2024\n\nחזרה לעברית."
    assert segment_by_language(text) == [
        ("he", "פסקה א.\n\nפסקה ב."),
        ("en", "English part.\n\n2024"),
        ("he", "חזרה לעברית."),
    ]


def test_chunk_respects_limit_and_loses_nothing():
    text = "\n\n".join(["משפט קצר. " * 40] * 10)
    chunks = chunk(text, max_chars=500)
    assert all(len(c) <= 500 for c in chunks)
    squash = lambda s: s.replace("\n", "").replace(" ", "")
    assert squash("".join(chunks)) == squash(text)


def test_chunk_splits_huge_sentence():
    chunks = chunk("מילה " * 1000, max_chars=300)
    assert all(len(c) <= 300 for c in chunks)
