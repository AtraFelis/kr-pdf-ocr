import pytest

from pdf_ocr.cli import deny_connection, parse_pages
from pdf_ocr.engine import LocalPaddleEngine
from pdf_ocr.pdf import render_pages


def test_page_ranges_and_duplicates():
    assert parse_pages("1, 3-5, 3") == [1, 3, 4, 5]


@pytest.mark.parametrize("value", ["0", "-1", "4-2", "1-2-3", "", "a"])
def test_invalid_pages(value):
    with pytest.raises(ValueError):
        parse_pages(value)


def test_network_is_denied():
    with pytest.raises(RuntimeError, match="네트워크"):
        deny_connection()


def test_missing_local_model_fails_before_initializing_runtime(tmp_path):
    with pytest.raises(FileNotFoundError, match="로컬 모델"):
        LocalPaddleEngine(tmp_path)


def test_out_of_range_pdf_page(tmp_path):
    from pypdf import PdfWriter

    path = tmp_path / "synthetic.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=240, height=360)
    writer.write(path)
    with pytest.raises(ValueError, match="페이지"):
        list(render_pages(path, [2], 72))
    [(number, image)] = list(render_pages(path, [1], 72))
    assert number == 1 and image.size == (240, 360)
    image.close()
