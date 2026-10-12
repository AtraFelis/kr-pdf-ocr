from pathlib import Path

import pypdfium2 as pdfium


def page_count(path: Path) -> int:
    try:
        with pdfium.PdfDocument(str(path)) as document:
            return len(document)
    except pdfium.PdfiumError as error:
        raise ValueError(
            f"PDF를 열 수 없습니다. 암호 또는 손상 여부를 확인하세요: {error}"
        ) from error


def render_pages(path: Path, pages: list[int], dpi: int):
    """Yield owned PIL images using one-based PDF page numbers."""
    with pdfium.PdfDocument(str(path)) as document:
        if any(number < 1 or number > len(document) for number in pages):
            raise ValueError(f"페이지 번호는 1~{len(document)} 사이여야 합니다.")
        for number in pages:
            page = document[number - 1]
            bitmap = page.render(scale=dpi / 72)
            try:
                yield number, bitmap.to_pil().copy()
            finally:
                bitmap.close()
                page.close()
