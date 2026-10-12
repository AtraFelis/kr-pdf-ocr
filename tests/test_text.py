from pdf_ocr.text import remove_hanja_annotations


def test_annotations_are_removed_but_korean_is_preserved():
    assert (
        remove_hanja_annotations("츠키히阿良良木月火의 괴이怪異 심체心體")
        == "츠키히의 괴이 심체"
    )


def test_parentheses_english_and_standalone_hanja():
    assert (
        remove_hanja_annotations("한국어(韓國語)와 한글（韓文）, 漢字, OCR(English)")
        == "한국어와 한글, 漢字, OCR(English)"
    )


def test_misrecognized_hangul_is_not_silently_removed():
    assert remove_hanja_annotations("츠키히 먹이 창제") == "츠키히 먹이 창제"


def test_paragraph_breaks_are_not_removed_as_annotation_spacing():
    assert remove_hanja_annotations("한국어\n\n(漢字)") == "한국어\n\n(漢字)"
