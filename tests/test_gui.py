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
    application = QApplication.instance() or QApplication([])
    configure_application(application)
    return application


@pytest.fixture
def window(application, tmp_path):
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
    path = tmp_path / "synthetic.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=450)
    writer.add_blank_page(width=450, height=300)
    writer.write(path)
    return path


@pytest.mark.parametrize("zoom", [0.5, 1, 1.5])
def test_reverse_mouse_drag_has_same_relative_region(application, zoom):
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
    window.load_pdf(pdf)
    window.editor.setPlainText("사용자가 편집한 내용")
    window.editor.document().setModified(True)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No
    )
    assert not window.load_pdf(pdf)
    assert window.editor.toPlainText() == "사용자가 편집한 내용"


def test_cancelled_run_recovers_completed_results(window, tmp_path):
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
    window.model.setCurrentIndex(window.model.findData("vl16"))
    assert not window.repair.isEnabled()
    window.model.setCurrentIndex(window.model.findData("paddle"))
    assert window.repair.isEnabled()


def test_corrupt_pdf_does_not_replace_loaded_document(
    window, pdf, tmp_path, monkeypatch
):
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
