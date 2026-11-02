from reader.clean import clean_text, strip_repeating_lines


def test_pdf_lines_rejoined_into_paragraph():
    raw = "זו שורה ראשונה של\nמשפט ארוך.\n\nפסקה שנייה."
    assert clean_text(raw, hard_wrapped=True) == "זו שורה ראשונה של משפט ארוך.\n\nפסקה שנייה."


def test_page_break_mid_sentence_is_joined():
    raw = "המשפט הזה נקטע\n\nבאמצע העמוד."
    assert clean_text(raw, hard_wrapped=True) == "המשפט הזה נקטע באמצע העמוד."


def test_page_numbers_removed():
    raw = "טקסט.\n12\nעמוד 3 מתוך 10\nPage 4 of 9\nעוד טקסט."
    assert clean_text(raw, hard_wrapped=False) == "טקסט.\n\nעוד טקסט."


def test_english_hyphenation_joined():
    assert clean_text("an impor-\ntant word.", hard_wrapped=True) == "an important word."


def test_web_text_keeps_lines_as_paragraphs():
    assert clean_text("כותרת\nפסקה.", hard_wrapped=False) == "כותרת\n\nפסקה."


def test_bidi_marks_removed():
    assert clean_text("\u200fשלום.\u200e", hard_wrapped=False) == "שלום."


def test_repeating_headers_stripped():
    pages = [f"עיתון הבוקר\nפתיחה של עמוד {i * 7} ייחודית.\nתוכן שונה {'א' * i}.\nסיום {i * 3}.\nעמוד {i}"
             for i in range(1, 5)]
    out = strip_repeating_lines(pages)
    assert all("עיתון הבוקר" not in p for p in out)
    assert "תוכן שונה א." in out[0] and "עמוד 1" not in out[0]


def test_rtl_leading_punctuation_moved_to_end():
    assert clean_text(".של מבוגרים בלילה", hard_wrapped=True) == "של מבוגרים בלילה."


def test_numbered_body_lines_are_kept():
    body = "\n".join(f"שורה מספר {n} בגוף." for n in range(10))
    pages = [f"כותרת\n{body}\nעמוד {i}" for i in range(1, 5)]
    out = strip_repeating_lines(pages)
    assert "שורה מספר 5 בגוף." in out[0]


# --- speakable(): no symbols read aloud, pauses kept ---
from reader.clean import speakable  # noqa: E402


def test_citations_removed():
    assert speakable("ירושלים היא עיר הבירה[1][2].") == "ירושלים היא עיר הבירה."
    assert speakable("נתון שנוי במחלוקת[דרוש מקור] כאן.") == "נתון שנוי במחלוקת כאן."


def test_parentheses_become_pauses_and_words_kept():
    assert speakable("העיר (בירת ישראל) גדולה.") == "העיר, בירת ישראל, גדולה."
    assert speakable("הוא נולד ב-1950 (בחיפה).") == "הוא נולד ב-1950, בחיפה."


def test_gershayim_and_geresh_kept():
    assert speakable('שירת בצה"ל ובארה״ב, ג\'ירפה.') == 'שירת בצה"ל ובארה״ב, ג\'ירפה.'


def test_quote_marks_removed():
    assert speakable('הוא אמר "שלום לכולם" ויצא.') == "הוא אמר שלום לכולם ויצא."


def test_dashes_and_symbols():
    assert speakable("המחקר – שפורסם אתמול – מפתיע.") == "המחקר, שפורסם אתמול, מפתיע."
    assert speakable("• סעיף ראשון * חשוב") == "סעיף ראשון חשוב"
    assert speakable("דו-שיח") == "דו-שיח"  # hyphen inside a word stays


def test_urls_removed():
    assert speakable("ראו https://example.com/a?b=1 לפרטים.") == "ראו לפרטים."


def test_punctuation_preserved_for_pauses():
    assert speakable("ראשון, שני; שלישי: רביעי! חמישי?") == "ראשון, שני; שלישי: רביעי! חמישי?"


def test_symbol_only_paragraph_dropped():
    assert clean_text("טקסט.\n***\nעוד.", hard_wrapped=False) == "טקסט.\n\nעוד."
