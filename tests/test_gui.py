"""Offscreen 화면에서 선택·편집·저장·취소·오류 처리 동작을 검증한다."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from pypdf import PdfWriter
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QSplitter

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


def test_coordinate_labels_stay_next_to_fields_when_widened(window, application):
    """창과 미리보기 폭을 늘려도 각 좌표 이름과 입력칸 사이 간격을 유지한다."""
    labels = {
        label.text(): label
        for label in window.findChildren(QLabel)
        if label.text() in ("왼쪽", "위쪽", "오른쪽", "아래쪽")
    }
    splitter = window.findChild(QSplitter)
    gaps = []
    widths = []
    for width in (1380, 2200):
        window.resize(width, 880)
        splitter.setSizes([240, width - 640, 400])
        application.processEvents()
        current_gaps = []
        for name, field in zip(
            ("왼쪽", "위쪽", "오른쪽", "아래쪽"), window.coordinates, strict=True
        ):
            label = labels[name]
            gap = field.mapToGlobal(QPoint()).x() - (
                label.mapToGlobal(QPoint()).x() + label.width()
            )
            assert 0 <= gap <= 12
            current_gaps.append(gap)
        gaps.append(current_gaps)
        widths.append(window.coordinates[0].width())
    assert gaps[0] == gaps[1]
    assert widths[1] > widths[0]


def test_detection_threshold_keeps_value_and_disables_unsupported_options(
    window, application
):
    """검출 값은 모델·형식 전환 후 유지하며 미지원 조합과 작업 중에는 잠근다."""
    assert window.det_box_thresh.value() == 0.5
    window.det_box_thresh.setValue(0.6)
    window.model.setCurrentIndex(window.model.findData("vl16"))
    assert not window.det_box_thresh.isEnabled()
    window.model.setCurrentIndex(window.model.findData("paddle"))
    assert window.det_box_thresh.isEnabled()
    application.processEvents()
    assert window.device_notice.height() >= window.device_notice.heightForWidth(
        window.device_notice.width()
    )
    assert window.det_box_thresh.value() == 0.6
    window.output_format.setCurrentIndex(window.output_format.findData("md"))
    assert not window.det_box_thresh.isEnabled()
    window.output_format.setCurrentIndex(window.output_format.findData("txt"))
    window.set_busy(True)
    assert not window.det_box_thresh.isEnabled()
    window.set_busy(False)
    assert window.det_box_thresh.value() == 0.6
    assert window.det_box_thresh.isEnabled()


@pytest.mark.parametrize("engine", ["paddle", "qwen"])
def test_gui_passes_detection_threshold_only_to_paddle(
    window, pdf, monkeypatch, engine
):
    """화면 입력값은 PP-OCRv5 작업 인자로만 고정하고 다른 모델에는 보내지 않는다."""
    import sys

    window.load_pdf(pdf)
    window.model.setCurrentIndex(window.model.findData(engine))
    window.det_box_thresh.setValue(0.6)
    window.dpi.setCurrentIndex(window.dpi.findData(400))
    monkeypatch.setattr("pdf_ocr.gui.ocr_python", lambda *args: sys.executable)
    calls = []
    monkeypatch.setattr(window.process, "start", lambda *args: calls.append(args))
    window.start_ocr()
    assert len(calls) == 1
    arguments = calls[0][1]
    assert arguments[arguments.index("--dpi") + 1] == "400"
    if engine == "paddle":
        assert arguments[arguments.index("--det-box-thresh") + 1] == "0.60"
    else:
        assert "--det-box-thresh" not in arguments


def test_dpi_reset_preserves_editor_and_selection(window):
    """해상도·검출 기본값 복원이 기존 편집 내용과 추출 영역을 변경하지 않는다."""
    window.dpi.setCurrentIndex(window.dpi.findData(600))
    window.det_box_thresh.setValue(0.4)
    window.editor.setPlainText("수정한 글자")
    original = Region(0, 0.2, 1, 0.8)
    window.preview.set_region(original)
    window.reset_ocr_settings()
    assert window.dpi.currentData() == 300
    assert window.det_box_thresh.value() == 0.5
    assert window.preview.region == original
    assert window.editor.toPlainText() == "수정한 글자"


def test_detection_overlay_uses_raw_page_coordinates(window, pdf, tmp_path):
    """전체 페이지 픽셀 좌표를 DPI·확대율과 독립적으로 표시하고 페이지 전환 때 지운다."""
    import json

    window.load_pdf(pdf)
    folder = tmp_path / "result"
    folder.mkdir()
    record = {
        "width": 1000,
        "height": 2000,
        "lines": [
            {
                "text": "본문",
                "polygon": [[200, 400], [800, 400], [800, 800], [200, 800]],
            },
            {"text": "좌표 없음", "polygon": None},
        ],
    }
    path = folder / "page-001.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    before = path.read_bytes()
    window.result_folder = folder
    window.show_detection.setChecked(True)
    assert window.preview.polygons[0][0].x() == 0.2
    assert window.preview.polygons[0][0].y() == 0.2
    window.preview.set_zoom(2)
    assert window.preview.polygons[0][0].x() == 0.2
    window.show_detection.setChecked(False)
    assert not window.preview.polygons
    window.show_detection.setChecked(True)
    window.page_list.setCurrentRow(1)
    assert not window.preview.polygons
    assert path.read_bytes() == before


def test_retry_drag_does_not_change_extraction_region(application):
    """역방향 재인식 드래그는 상대 영역만 만들고 기존 추출 영역은 보존한다."""
    widget = PagePreview()
    with Image.new("RGB", (400, 600), "white") as image:
        widget.set_image(image)
    original = Region(0, 0.1, 1, 0.9)
    widget.set_region(original)
    widget.set_retry_mode(True)
    selections = []
    widget.retry_region_changed.connect(selections.append)
    widget.show()
    application.processEvents()
    QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=QPoint(336, 496))
    QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=QPoint(96, 136))
    assert selections[0].values() == pytest.approx([0.2, 0.2, 0.8, 0.8])
    assert widget.region == original
    widget.clear_image()
    assert widget.retry_region is None
    widget.close()


@pytest.mark.parametrize("value", [float("nan"), -0.1, 1.1])
def test_detection_overlay_rejects_invalid_relative_coordinates(application, value):
    """손상된 좌표를 표시용 다각형이나 신뢰도로 생성하지 않고 거부한다."""
    widget = PagePreview()
    with pytest.raises(ValueError, match="상대 좌표"):
        widget.set_polygons([[[value, 0.1], [0.8, 0.1], [0.8, 0.2]]])
    assert not widget.polygons
    widget.close()


@pytest.mark.parametrize("clipped", [False, True])
def test_arbitrary_retry_arguments_candidate_and_safe_insertion(
    window, pdf, tmp_path, monkeypatch, clipped
):
    """새 영역 작업의 인자·토큰 잘림 거부·명시적 삽입·실행 취소와 원본 보존을 확인한다."""
    import json
    import sys

    from PySide6.QtCore import QProcess

    from pdf_ocr.region_retry_ui import RegionRetryDialog

    region = Region(0, 0.2, 1, 0.8)
    window.editor.setPlainText("편집본")
    dlg = RegionRetryDialog(
        tmp_path, pdf, 1, region, 400, "gpu", 0.45, "paddle", window
    )
    calls = []
    monkeypatch.setattr(
        "pdf_ocr.region_retry_ui.ocr_python", lambda *args: sys.executable
    )
    monkeypatch.setattr(dlg.process, "start", lambda *args: calls.append(args))
    dlg.start()
    arguments = calls[0][1]
    assert arguments[arguments.index("--dpi") + 1] == "400"
    assert arguments[arguments.index("--region") + 1] == "0,0.2,1,0.8"
    assert arguments[arguments.index("--det-box-thresh") + 1] == "0.45"
    assert "--keep-line-breaks" in arguments
    assert not dlg.model.isEnabled()
    dlg.active_folder.mkdir()
    (dlg.active_folder / "page-001.json").write_text(
        json.dumps({"lines": [{"text": "새 후보", "token_limit_reached": clipped}]}),
        encoding="utf-8",
    )
    with Image.new("RGB", (80, 20), "white") as image:
        image.save(dlg.active_folder / "page-001-input.png")
    dlg.process.finished.emit(0, QProcess.ExitStatus.NormalExit)
    assert window.editor.toPlainText() == "편집본"
    if clipped:
        assert not dlg.candidates
        assert not dlg.insert_button.isEnabled()
        assert "잘렸" in dlg.status.text()
    else:
        assert dlg.candidates[0]["text"] == "새 후보"
        cursor = window.editor.textCursor()
        cursor.select(cursor.SelectionType.Document)
        window.editor.setTextCursor(cursor)
        dlg.insert_candidate()
        assert window.editor.toPlainText() == "편집본새 후보"
        window.editor.undo()
        assert window.editor.toPlainText() == "편집본"
    assert pdf.is_file()
    dlg.close()


def test_region_retry_cancel_preserves_editor_and_previous_candidates(
    window, pdf, tmp_path, monkeypatch
):
    """실제 소유 프로세스를 취소해 완료 신호·취소 안내와 기존 편집/후보 보존을 확인한다."""
    import sys

    from PySide6.QtCore import QProcess

    from pdf_ocr.region_retry_ui import RegionRetryDialog

    window.editor.setPlainText("편집본")
    dlg = RegionRetryDialog(
        tmp_path, pdf, 1, Region(), 300, "cpu", 0.5, "paddle", window
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            "pdf_ocr.region_retry_ui.ocr_python", lambda *args: sys.executable
        )
        patch.setattr(dlg.process, "start", lambda *args: None)
        dlg.start()
    dlg.candidates.append({"text": "이전 후보", "folder": tmp_path})
    dlg.process.start(sys.executable, ["-c", "import time; time.sleep(30)"])
    assert dlg.process.waitForStarted(3000)
    dlg.cancel()
    for _ in range(150):
        QTest.qWait(20)
        if dlg.run_button.isEnabled():
            break
    assert dlg.process.state() == QProcess.ProcessState.NotRunning
    assert "취소" in dlg.status.text()
    assert dlg.candidates[0]["text"] == "이전 후보"
    assert window.editor.toPlainText() == "편집본"
    dlg.close()


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


def test_dictionary_snapshot_stays_fixed_and_vlm_disables_selection(window, tmp_path):
    """작업 사전이 이후 편집과 분리되며 VLM에서는 선택을 비활성화한다."""
    from pdf_ocr.dictionary import UserDictionary, load_dictionary, save_dictionary

    path = tmp_path / "user_data" / "dictionaries" / "example.json"
    initial = UserDictionary("예시", ("하루카",))
    save_dictionary(path, initial)
    window.refresh_dictionaries(path)
    session = tmp_path / "snapshot"
    session.mkdir()
    snapshot = window.dictionary_snapshot(session)
    save_dictionary(path, UserDictionary("변경", ("푸른별 연구소",)), overwrite=True)
    assert load_dictionary(snapshot) == initial
    window.model.setCurrentIndex(window.model.findData("vl16"))
    assert not window.dictionary_choice.isEnabled()
    window.model.setCurrentIndex(window.model.findData("paddle"))
    assert window.dictionary_choice.isEnabled()


def test_dictionary_dialog_save_conflict_and_discard(
    application, tmp_path, monkeypatch
):
    """사전 저장·단어 편집과 충돌 거부·미저장 닫기 확인을 검증한다."""
    from pdf_ocr.dictionary import load_dictionary
    from pdf_ocr.dictionary_ui import DictionaryDialog

    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[2]))
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No
    )
    dialog = DictionaryDialog(tmp_path / "dictionaries")
    dialog.name.setText("합성 사전")
    dialog.words.setPlainText("하루카\n하루카\n푸른별 연구소")
    dialog.save()
    assert load_dictionary(dialog.selected).words == ("하루카", "푸른별 연구소")
    before = dialog.selected.read_bytes()
    dialog.words.setPlainText("푸른별연구소\n푸른별 연구소")
    dialog.save()
    assert messages and dialog.selected.read_bytes() == before
    dialog.show()
    application.processEvents()
    dialog.reject()
    assert dialog.isVisible()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes
    )
    dialog.reject()
    assert not dialog.isVisible()


def test_bad_dictionary_txt_import_keeps_editor(application, tmp_path, monkeypatch):
    """잘못된 TXT 가져오기로 기존 사전 편집을 지우지 않는다."""
    from PySide6.QtWidgets import QFileDialog

    from pdf_ocr.dictionary_ui import DictionaryDialog

    source = tmp_path / "invalid.txt"
    source.write_bytes(b"\xff")
    dialog = DictionaryDialog(tmp_path / "dictionaries")
    dialog.name.setText("기존")
    dialog.words.setPlainText("하루카")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(source), ""))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: None)
    dialog.import_txt()
    assert dialog.words.toPlainText() == "하루카"
    assert dialog.name.text() == "기존"
    dialog.clean = (dialog.name.text(), dialog.words.toPlainText())
    dialog.close()


def test_real_reprocess_preserves_user_edit(window, tmp_path, monkeypatch):
    """실제 재보정 프로세스가 현재 편집을 유지하고 별도 비교 결과를 생성한다."""
    import json

    from PySide6.QtCore import QProcess

    from pdf_ocr.dictionary import UserDictionary, save_dictionary
    from pdf_ocr.dictionary_ui import ComparisonDialog

    source = tmp_path / "page-001.json"
    record = {
        "page": 1,
        "lines": [
            {
                "text": "푸른별연구소에서 하루카를 만났다.",
                "polygon": [[0, 0], [500, 0], [500, 20], [0, 20]],
            }
        ],
    }
    source.write_text(json.dumps(record), encoding="utf-8")
    path = tmp_path / "user_data" / "dictionaries" / "example.json"
    save_dictionary(path, UserDictionary("예시", ("푸른별 연구소", "하루카")))
    window.refresh_dictionaries(path)
    window.editor.setPlainText("사용자 편집본")
    window.editor.document().setModified(True)
    compared = []
    monkeypatch.setattr(
        ComparisonDialog, "exec", lambda self: compared.append(self.windowTitle())
    )
    window.start_reprocess(source)
    assert window.process.waitForStarted(3000)
    for _ in range(1200):
        QTest.qWait(25)
        if window.process.state() == QProcess.ProcessState.NotRunning:
            break
    if window.running():
        window.process.kill()
        window.process.waitForFinished(3000)
        pytest.fail("재보정 실행 시간 초과")
    assert window.process.exitCode() == 0, window.log_buffer
    assert compared
    assert window.editor.toPlainText() == "사용자 편집본"
    assert window.editor.document().isModified()
    assert "푸른별 연구소" in (window.comparison_folder / "combined.txt").read_text(
        encoding="utf-8"
    )
    assert "재보정 완료" in window.status.text()


def test_dictionary_delete_and_export(application, tmp_path, monkeypatch):
    """저장 사전의 UTF-8 내보내기와 확인된 삭제를 검증한다."""
    from PySide6.QtWidgets import QFileDialog

    from pdf_ocr.dictionary_ui import DictionaryDialog

    dialog = DictionaryDialog(tmp_path / "dictionaries")
    dialog.name.setText("예시")
    dialog.words.setPlainText("하루카\n푸른별 연구소")
    dialog.save()
    path = dialog.selected
    export = tmp_path / "words.txt"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(export), "")
    )
    dialog.export_txt()
    assert export.read_text(encoding="utf-8") == "하루카\n푸른별 연구소\n"
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No
    )
    dialog.delete()
    assert path.exists()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes
    )
    dialog.delete()
    assert not path.exists() and dialog.selected is None
    dialog.close()


def test_cancelled_reprocess_keeps_edit_and_comparison(window, tmp_path, monkeypatch):
    """취소된 재보정의 완료 비교 결과를 열어도 현재 편집본을 유지한다."""
    from PySide6.QtCore import QProcess

    from pdf_ocr.dictionary_ui import ComparisonDialog

    folder = tmp_path / "comparison" / "result"
    folder.mkdir(parents=True)
    for name in ("combined.txt", "without-dictionary.txt", "before-spacing.txt"):
        (folder / name).write_text("완료된 비교 결과", encoding="utf-8")
    window.comparison_folder = folder
    window.job_kind = "reprocess"
    window.cancelled = True
    window.editor.setPlainText("보호할 편집본")
    window.editor.document().setModified(True)
    monkeypatch.setattr(ComparisonDialog, "exec", lambda self: None)
    window.process_finished(1, QProcess.ExitStatus.CrashExit)
    assert window.editor.toPlainText() == "보호할 편집본"
    assert window.editor.document().isModified()
    assert "취소" in window.status.text()


def test_comparison_export_confirmation(application, tmp_path, monkeypatch):
    """별도 비교 결과 저장은 덮어쓰기 확인을 따르며 기존 출력을 보호한다."""
    from PySide6.QtWidgets import QFileDialog

    from pdf_ocr.dictionary_ui import ComparisonDialog

    folder = tmp_path / "comparison"
    folder.mkdir()
    for name in ("combined.txt", "without-dictionary.txt", "before-spacing.txt"):
        (folder / name).write_text("합성 재보정 결과", encoding="utf-8")
    dialog = ComparisonDialog(folder)
    target = tmp_path / "saved.txt"
    target.write_text("기존 결과", encoding="utf-8")
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), "")
    )
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No
    )
    dialog.save_result()
    assert target.read_text(encoding="utf-8") == "기존 결과"
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes
    )
    dialog.save_result()
    assert target.read_text(encoding="utf-8") == "합성 재보정 결과"
    dialog.close()
