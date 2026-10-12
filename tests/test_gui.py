"""Offscreen 화면에서 선택·편집·저장·취소·오류 처리 동작을 검증한다."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from pypdf import PdfWriter
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from pdf_ocr.gui import OCRWindow, configure_application
from pdf_ocr.preview import PagePreview
from pdf_ocr.selection import Region


@pytest.fixture(scope="module")
def application():
    """모듈의 화면 검사에 사용할 밝은 테마 QApplication을 준비한다."""
    application = QApplication.instance() or QApplication([])
    configure_application(application)
    return application


@pytest.fixture
def window(application, tmp_path):
    """임시 작업 루트의 창을 제공하고 검사 뒤 편집 상태를 정리해 닫는다."""
    window = OCRWindow(root=tmp_path)
    window.show()
    application.processEvents()
    yield window
    window.editor.document().setModified(False)
    window.close()
    window.deleteLater()
    application.processEvents()


@pytest.fixture
def pdf(tmp_path):
    """가로·세로 크기가 다른 두 빈 페이지의 합성 PDF를 만든다."""
    path = tmp_path / "synthetic.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=450)
    writer.add_blank_page(width=450, height=300)
    writer.write(path)
    return path


@pytest.mark.parametrize("zoom", [0.5, 1, 1.5])
def test_reverse_mouse_drag_has_same_relative_region(application, zoom):
    """역방향 드래그와 확대 변화에도 상대 선택 범위가 같은지 확인한다."""
    widget = PagePreview()
    with Image.new("RGB", (400, 600), "white") as image:
        widget.set_image(image)
    widget.set_zoom(zoom)
    widget.show()
    application.processEvents()
    end = QPoint(round(16 + 400 * zoom * 0.2), round(16 + 600 * zoom * 0.2))
    start = QPoint(round(16 + 400 * zoom * 0.8), round(16 + 600 * zoom * 0.8))
    QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(widget, end)
    QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=end)
    assert widget.region.values() == pytest.approx([0.2, 0.2, 0.8, 0.8])
    widget.set_zoom(2)
    assert widget.region.values() == pytest.approx([0.2, 0.2, 0.8, 0.8])
    widget.close()


def test_pdf_page_checks_and_region_scope(window, pdf):
    """페이지 제외 체크와 모든 페이지 영역 적용이 미리보기에 반영되는지 확인한다."""
    assert window.load_pdf(pdf)
    window.pages_field.setText("1-2")
    window.exclude_field.setText("2")
    assert window.apply_page_fields()
    assert window.checked_pages() == [1]
    selected = Region(0, 0.2, 1, 0.8)
    window.selection_changed(selected)
    window.scope.setCurrentIndex(2)
    window.apply_region(selected)
    window.page_list.setCurrentRow(1)
    assert window.preview.region == selected
    assert window.regions == {1: selected, 2: selected}


def test_edit_save_preserves_pdf_and_protects_existing_output(window, pdf, tmp_path):
    """UTF-8 편집 저장과 원본 PDF·기존 출력 덮어쓰기 보호를 확인한다."""
    before = pdf.read_bytes()
    window.load_pdf(pdf)
    window.editor.setPlainText("한글 결과\n\n수정한 문단")
    target = tmp_path / "result.txt"
    window.save_result(target)
    assert target.read_text(encoding="utf-8") == window.editor.toPlainText()
    assert pdf.read_bytes() == before
    window.editor.insertPlainText(" 추가")
    with pytest.raises(FileExistsError):
        window.save_result(target)
    with pytest.raises(ValueError):
        window.save_result(pdf, overwrite=True)
    assert pdf.read_bytes() == before


def test_unsaved_edit_is_preserved_when_new_pdf_is_rejected(window, pdf, monkeypatch):
    """편집 폐기를 거부하면 새 PDF를 열지 않고 수정 내용을 유지하는지 확인한다."""
    window.load_pdf(pdf)
    window.editor.setPlainText("사용자가 편집한 내용")
    window.editor.document().setModified(True)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No
    )
    assert not window.load_pdf(pdf)
    assert window.editor.toPlainText() == "사용자가 편집한 내용"


def test_cancelled_run_recovers_completed_results(window, tmp_path):
    """취소 상태에서도 이미 완료된 통합 결과를 복구하는지 확인한다."""
    folder = tmp_path / "job" / "result"
    folder.mkdir(parents=True)
    (folder / "combined.txt").write_text("완료된 페이지", encoding="utf-8")
    window.run_folder = folder
    window.cancelled = True
    window.log_buffer = "page=1 lines=3 seconds=1.0\n"
    from PySide6.QtCore import QProcess

    window.process_finished(1, QProcess.ExitStatus.CrashExit)
    assert window.editor.toPlainText() == "완료된 페이지"
    assert "취소됨" in window.status.text()


def test_generated_model_disables_inapplicable_spacing_option(window):
    """선택 모델에 맞춰 사용할 수 없는 별도 띄어쓰기 보정을 끄는지 확인한다."""
    window.model.setCurrentIndex(window.model.findData("vl16"))
    assert not window.repair.isEnabled()
    window.model.setCurrentIndex(window.model.findData("paddle"))
    assert window.repair.isEnabled()


def test_corrupt_pdf_does_not_replace_loaded_document(
    window, pdf, tmp_path, monkeypatch
):
    """손상 PDF 열기 실패가 기존 로드 문서를 바꾸지 않는지 확인한다."""
    window.load_pdf(pdf)
    damaged = tmp_path / "damaged.pdf"
    damaged.write_bytes(b"not a PDF")
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[2]))
    assert not window.load_pdf(damaged)
    assert window.pdf_path == pdf.resolve() and messages


def test_failed_ocr_retains_partial_text_and_reports_failure(
    window, tmp_path, monkeypatch
):
    """OCR 실패를 성공으로 표시하지 않고 완료된 일부 텍스트를 유지하는지 확인한다."""
    from PySide6.QtCore import QProcess

    folder = tmp_path / "failed" / "result"
    folder.mkdir(parents=True)
    (folder / "combined.txt").write_text("완료된 부분", encoding="utf-8")
    window.run_folder = folder
    window.log_buffer = "model error"
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    window.process_finished(1, QProcess.ExitStatus.NormalExit)
    assert "중단" in window.status.text()
    assert window.editor.toPlainText() == "완료된 부분"


def test_real_process_cancel_preserves_partial_result(window, tmp_path):
    """실제 소유 프로세스를 취소해도 완료 페이지 수와 저장한 결과가 남는지 확인한다."""
    import sys

    from PySide6.QtCore import QProcess

    window.run_folder = tmp_path / "job" / "result"
    window.run_folder.mkdir(parents=True)
    (window.run_folder / "combined.txt").write_text("완료된 결과", encoding="utf-8")
    window.progress.setRange(0, 2)
    window.process.start(
        sys.executable,
        [
            "-u",
            "-c",
            "import time; print('page=1 lines=1 seconds=1.0',flush=True); time.sleep(30)",
        ],
    )
    assert window.process.waitForStarted(3000)
    for _ in range(100):
        QTest.qWait(10)
        if window.completed:
            break
    window.cancel_ocr()
    for _ in range(350):
        QTest.qWait(10)
        if window.process.state() == QProcess.ProcessState.NotRunning:
            break
    assert window.process.state() == QProcess.ProcessState.NotRunning
    assert window.editor.toPlainText() == "완료된 결과"
    assert window.progress.value() == 1 and window.progress.maximum() == 2
    assert "취소됨" in window.status.text()
