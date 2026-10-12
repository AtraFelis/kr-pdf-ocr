"""페이지 번호 검사·네트워크 차단·로컬 모델 누락 처리를 검증한다."""

import pytest

from pdf_ocr.cli import deny_connection
from pdf_ocr.engine import LocalPaddleEngine
from pdf_ocr.pdf import render_pages
from pdf_ocr.selection import parse_pages


def test_page_ranges_and_duplicates():
    """1 기반 페이지 범위의 입력 순서와 중복 제거를 확인한다."""
    assert parse_pages("1, 3-5, 3") == [1, 3, 4, 5]


@pytest.mark.parametrize("value", ["0", "-1", "4-2", "1-2-3", "", "a"])
def test_invalid_pages(value):
    """음수·역순·잘못된 형식의 페이지 입력을 거부하는지 확인한다."""
    with pytest.raises(ValueError):
        parse_pages(value)


def test_network_is_denied():
    """문서 처리의 소켓 연결 차단 함수가 항상 실패를 알리는지 확인한다."""
    with pytest.raises(RuntimeError, match="네트워크"):
        deny_connection()


def test_missing_local_model_fails_before_initializing_runtime(tmp_path):
    """로컬 모델 누락이 OCR 라이브러리 초기화 전에 안내되는지 확인한다."""
    with pytest.raises(FileNotFoundError, match="로컬 모델"):
        LocalPaddleEngine(tmp_path)


def test_out_of_range_pdf_page(tmp_path):
    """범위 밖 페이지를 거부하고 유효한 페이지의 렌더링 크기를 확인한다."""
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
