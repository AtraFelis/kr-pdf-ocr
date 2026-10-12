"""합성 결과로 구조 좌표·Markdown 이미지 저장·미리보기·실패 보존을 검증한다."""

import json
import os
from types import SimpleNamespace
from urllib.parse import unquote

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtCore import QProcess, QUrl
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QApplication, QMessageBox

from pdf_ocr import structure
from pdf_ocr.gui import OCRWindow, configure_application
from pdf_ocr.markdown_export import MarkdownPreview, save_markdown
from pdf_ocr.model_info import ModelInfoDialog
from pdf_ocr.selection import Region


def test_later_structure_failure_keeps_first_page_and_failed_summary(
    tmp_path, monkeypatch
):
    """뒤 페이지 실패 시 앞 페이지·원시 결과·실패 요약과 영역 설정을 보존한다."""

    class FailingEngine:
        """첫 페이지만 성공시키는 합성 구조 분석 대역이다."""

        def __init__(self, root, device):
            """실제 모델 없이 장치와 호출 수를 기록한다."""
            self.device = device
            self.calls = 0

        def recognize(self, image):
            """첫 호출에 합성 결과를 반환하고 두 번째 호출에서는 실패한다."""
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("합성 실패")
            return synthetic_result()

    def rendered(*args):
        """외부 문서 없는 두 합성 페이지를 렌더링 결과로 제공한다."""
        for number in (1, 2):
            yield number, Image.new("RGB", (1000, 1000), "white")

    monkeypatch.setattr(structure, "LocalStructureEngine", FailingEngine)
    monkeypatch.setattr(structure, "render_pages", rendered)
    output = tmp_path / "new"
    output.mkdir()
    args = SimpleNamespace(
        device="cpu", pdf=tmp_path / "unused.pdf", dpi=300, output=output
    )
    with pytest.raises(RuntimeError, match="합성 실패"):
        structure.run_structure(args, tmp_path, [1, 2], Region(0, 0.2, 1, 0.8), {})
    first = json.loads((output / "page-001.json").read_text(encoding="utf-8"))
    assert first["region_pixel_box"] == [0, 200, 1000, 800]
    assert first["region"] == [0, 0.2, 1, 0.8]
    assert (output / "combined.md").read_text(encoding="utf-8") == first["markdown"]
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["state"] == "failed" and summary["completed_pages"] == [1]
    assert not (output / "page-002.md").exists()


@pytest.fixture(scope="module")
def application():
    """실제 화면을 띄우지 않고 Qt 이미지·저장·설정 동작을 확인할 앱을 준비한다."""
    app = QApplication.instance() or QApplication([])
    configure_application(app)
    return app


def synthetic_result():
    """모델 출력과 같은 형식의 합성 표·수식·이미지 블록을 반환한다."""
    return SimpleNamespace(
        json={
            "res": {
                "parsing_res_list": [
                    {
                        "block_label": "table",
                        "block_content": "<table><tr><td>합성</td></tr></table>",
                        "block_bbox": [10, 20, 110, 120],
                        "block_order": 1,
                    },
                    {
                        "block_label": "formula",
                        "block_content": "$x^2$",
                        "block_bbox": [10, 130, 80, 160],
                        "block_order": 2,
                    },
                ]
            }
        },
        markdown={
            "markdown_texts": "# 합성\n\n<table><tr><td>합성</td></tr></table>\n\n$x^2$\n\n![그림](imgs/a.png)",
            "markdown_images": {"imgs/a.png": Image.new("RGB", (12, 10), "red")},
        },
    )


def test_structure_offsets_preserve_raw_and_block_order(tmp_path):
    """영역의 입력·전체·상대 좌표를 구분하고 원시 구조·표·수식을 유지한다."""
    result = synthetic_result()
    before = json.dumps(result.json, ensure_ascii=False)
    record = structure.save_structure(
        result, tmp_path, 3, (100, 200, 500, 800), 1000, 1000
    )
    assert record["blocks"][0]["bbox_in_input"] == [10, 20, 110, 120]
    assert record["blocks"][0]["bbox"] == [110, 220, 210, 320]
    assert record["blocks"][0]["relative_bbox"] == [0.11, 0.22, 0.21, 0.32]
    assert [b["order"] for b in record["blocks"]] == [1, 2]
    assert "<table>" in record["markdown"] and "$x^2$" in record["markdown"]
    assert "assets/page-003-001.png" in record["markdown"]
    assert (tmp_path / "assets/page-003-001.png").is_file()
    assert json.dumps(result.json, ensure_ascii=False) == before
    assert (
        json.loads((tmp_path / "page-003-native.json").read_text(encoding="utf-8"))
        == result.json["res"]
    )
    result.markdown["markdown_images"]["imgs/a.png"].close()


def test_missing_image_fails_without_losing_native_json(tmp_path):
    """그림 데이터 누락은 성공으로 표시하지 않으며 이미 인식한 원시 결과는 남긴다."""
    result = synthetic_result()
    result.markdown["markdown_images"]["imgs/a.png"].close()
    result.markdown["markdown_images"]["imgs/a.png"] = None
    with pytest.raises(ValueError, match="이미지 데이터"):
        structure.save_structure(result, tmp_path, 1, (0, 0, 200, 200), 200, 200)
    assert (tmp_path / "page-001-native.json").is_file()
    assert not (tmp_path / "page-001.md").exists()


def create_asset(root, color="red"):
    """로컬 이미지 경로·캐시 검사를 위한 합성 PNG를 만든다."""
    assets = root / "assets"
    assets.mkdir(parents=True)
    with Image.new("RGB", (12, 10), color) as image:
        image.save(assets / "a.png")
    return assets / "a.png"


def test_bundle_export_escapes_names_and_protects_existing(application, tmp_path):
    """한글·공백 파일명과 HTML/Markdown 그림을 함께 내보내고 기존 출력을 보호한다."""
    source = tmp_path / "source"
    asset = create_asset(source)
    before = asset.read_bytes()
    target = tmp_path / "합성 문서.md"
    text = '![그림](assets/a.png)\n<img src="assets/a.png" />'
    save_markdown(target, text, source)
    saved = target.read_text(encoding="utf-8")
    assert "assets/a.png" not in saved
    reference = saved.split("](")[1].split(")")[0]
    assert "%20" in reference
    assert (tmp_path / unquote(reference)).read_bytes() == before
    with pytest.raises(FileExistsError):
        save_markdown(target, "덮어쓰기", source)
    assert target.read_text(encoding="utf-8") == saved
    save_markdown(target, "승인된 변경", source, overwrite=True)
    assert asset.read_bytes() == before
    assert (tmp_path / unquote(reference)).is_file()


def test_export_rejects_traversal_and_missing_assets(application, tmp_path):
    """결과 밖 이미지·누락 이미지는 파일을 만들기 전에 거부한다."""
    source = tmp_path / "source"
    create_asset(source)
    (tmp_path / "secret.png").write_bytes(b"private")
    for reference in ("assets/../../secret.png", "assets/missing.png"):
        target = tmp_path / "bad.md"
        with pytest.raises(ValueError):
            save_markdown(target, f"![그림]({reference})", source)
        assert not target.exists()


def test_preview_accepts_only_local_result_images(application, tmp_path):
    """원격·결과 밖 이미지 자원은 거부하고 내부 이미지는 표시한다."""
    source = tmp_path / "source"
    create_asset(source)
    preview = MarkdownPreview()
    preview.display("![그림](assets/a.png)", source)
    kind = QTextDocument.ResourceType.ImageResource
    image = preview.document().resource(kind, QUrl("assets/a.png"))
    assert image is not None and not image.isNull()
    assert preview.loadResource(kind, QUrl("https://example.com/image.png")) is None
    assert (
        preview.loadResource(kind, QUrl.fromLocalFile(str(tmp_path / "secret.png")))
        is None
    )
    preview.close()


def test_preview_reloading_different_root_does_not_reuse_old_image(
    application, tmp_path
):
    """동일 상대 이미지 이름의 새 작업을 열면 이전 작업의 그림이 표시되지 않는다."""
    first, second = tmp_path / "first", tmp_path / "second"
    create_asset(first, "red")
    create_asset(second, "blue")
    preview = MarkdownPreview()
    preview.display("![그림](assets/a.png)", first)
    kind = QTextDocument.ResourceType.ImageResource
    preview.document().resource(kind, QUrl("assets/a.png"))
    preview.display("![그림](assets/a.png)", second)
    image = preview.document().resource(kind, QUrl("assets/a.png"))
    image = image.toImage() if hasattr(image, "toImage") else image
    assert image.pixelColor(0, 0).name() == "#0000ff"
    preview.close()


def test_gui_result_format_is_independent_of_next_job(application, tmp_path):
    """다음 작업 형식을 바꿔도 이미 편집 중인 Markdown·표시 형식을 보존한다."""
    window = OCRWindow(root=tmp_path)
    window.result_format = "md"
    window.editor.setPlainText("# 합성 결과")
    window.output_format.setCurrentIndex(window.output_format.findData("txt"))
    path = tmp_path / "saved.md"
    window.save_result(path)
    assert path.read_text(encoding="utf-8") == "# 합성 결과"
    assert window.result_format == "md"
    window.editor.document().setModified(False)
    window.close()


def test_cancelled_md_job_loads_partial_result(application, tmp_path):
    """취소한 구조 분석의 완료 Markdown을 읽고 저장할 수 있게 유지한다."""
    window = OCRWindow(root=tmp_path)
    folder = tmp_path / "job" / "result"
    folder.mkdir(parents=True)
    (folder / "combined.md").write_text("# 완료된 페이지", encoding="utf-8")
    window.run_folder = folder
    window.result_folder = folder
    window.result_format = "md"
    window.cancelled = True
    window.log_buffer = "page=1 lines=2 seconds=1.0\n"
    window.process_finished(1, QProcess.ExitStatus.CrashExit)
    assert window.editor.toPlainText() == "# 완료된 페이지"
    assert "취소" in window.status.text()
    assert window.save_button.isEnabled()
    window.editor.document().setModified(False)
    window.close()


def test_invalid_md_model_preserves_editor(application, tmp_path, monkeypatch):
    """미지원 모델의 Markdown 실행은 편집 내용·출력 선택을 유지하고 거부한다."""
    window = OCRWindow(root=tmp_path)
    window.editor.setPlainText("편집본")
    window.output_format.setCurrentIndex(window.output_format.findData("md"))
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[2]))
    window.start_ocr()
    assert messages and not window.running()
    assert window.editor.toPlainText() == "편집본"
    assert window.output_format.currentData() == "md"
    window.editor.document().setModified(False)
    window.close()


def test_model_info_open_close_preserves_settings(application, tmp_path, monkeypatch):
    """모델 설명의 열기·닫기와 초점 복귀가 선택값·편집 내용을 바꾸지 않는다."""
    window = OCRWindow(root=tmp_path)
    window.show()
    application.processEvents()
    window.editor.setPlainText("편집본")
    monkeypatch.setattr(ModelInfoDialog, "exec", lambda self: 0)
    before = (
        window.model.currentData(),
        window.device.currentData(),
        window.output_format.currentData(),
    )
    window.show_model_info()
    application.processEvents()
    assert before == (
        window.model.currentData(),
        window.device.currentData(),
        window.output_format.currentData(),
    )
    assert window.editor.toPlainText() == "편집본"
    assert window.model_info_button.hasFocus()
    window.editor.document().setModified(False)
    window.close()


def test_html_percent_image_preview_does_not_overlay_heading(application, tmp_path):
    """백분율 HTML 그림을 독립 문단으로 표시하고 제목과 겹치지 않게 축소한다."""
    source = tmp_path / "source"
    assets = source / "assets"
    assets.mkdir(parents=True)
    with Image.new("RGB", (200, 100), "red") as image:
        image.save(assets / "a.png")
    preview = MarkdownPreview()
    preview.resize(500, 400)
    preview.show()
    application.processEvents()
    text = '<div style="text-align: center;"><img src="assets/a.png" width="4%" /></div>\n\n## 다음 제목'
    preview.display(text, source)
    application.processEvents()
    kind = QTextDocument.ResourceType.ImageResource
    image = preview.document().resource(kind, QUrl("assets/a.png"))
    assert image.width() <= 25
    first = preview.document().firstBlock()
    heading = preview.document().findBlockByNumber(1)
    assert "다음 제목" in heading.text()
    layout = preview.document().documentLayout()
    assert (
        layout.blockBoundingRect(heading).top()
        >= layout.blockBoundingRect(first).bottom()
    )
    assert text.startswith("<div")
    preview.display(text.replace("4%", "40%"), source)
    application.processEvents()
    larger = preview.document().resource(kind, QUrl("assets/a.png"))
    assert larger.width() > image.width()
    preview.resize(250, 400)
    application.processEvents()
    resized = preview.document().resource(kind, QUrl("assets/a.png"))
    assert resized.width() < larger.width()
    preview.display(text.replace("4%", "1..2%"), source)
    assert "다음 제목" in preview.toPlainText()
    preview.close()


def test_preview_document_blocks_real_outside_file(application, tmp_path):
    """실제 이미지가 결과 밖에 있어도 Qt 문서 자체가 읽지 못하게 한다."""
    source = tmp_path / "source"
    create_asset(source)
    outside = tmp_path / "private.png"
    with Image.new("RGB", (10, 10), "green") as image:
        image.save(outside)
    preview = MarkdownPreview()
    preview.display(
        "![외부](../private.png)\n\n![원격](https://example.com/a.png)", source
    )
    kind = QTextDocument.ResourceType.ImageResource
    (source / "assets" / "a.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8"
    )
    assert preview.document().resource(kind, QUrl("assets/a.svg")) is None
    assert preview.document().resource(kind, QUrl("../private.png")) is None
    assert preview.document().resource(kind, QUrl("https://example.com/a.png")) is None
    preview.close()


def test_model_info_keyboard_opens_real_dialog(application, tmp_path):
    """Space로 실제 설명 창을 열고 닫은 뒤 초점·편집 내용이 보존되는지 확인한다."""
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtTest import QTest

    window = OCRWindow(root=tmp_path)
    window.show()
    window.editor.setPlainText("편집본")
    application.processEvents()
    window.model.setFocus()
    QTest.keyClick(window.model, Qt.Key.Key_Tab)
    assert window.model_info_button.hasFocus()
    opened = []

    def close_dialog():
        """중첩 이벤트 루프의 실제 모델 설명 창을 닫고 열린 상태를 기록한다."""
        dialog = QApplication.activeModalWidget()
        if isinstance(dialog, ModelInfoDialog):
            opened.append(dialog.windowTitle())
            QTest.keyClick(dialog, Qt.Key.Key_Escape)

    timer = QTimer(window)
    timer.setSingleShot(True)
    timer.timeout.connect(close_dialog)
    timer.start(0)
    QTest.keyClick(window.model_info_button, Qt.Key.Key_Space)
    application.processEvents()
    assert opened
    assert window.model_info_button.hasFocus()
    assert window.editor.toPlainText() == "편집본"
    window.editor.document().setModified(False)
    window.close()


@pytest.mark.parametrize(
    "extra",
    [
        [],
        ["--engine", "qwen"],
        ["--engine", "vl16", "--repair-spacing"],
        ["--engine", "vl16", "--vl-lines"],
        ["--engine", "vl16", "--dictionary", "missing.json"],
    ],
)
def test_cli_invalid_markdown_combinations_fail_before_output(
    tmp_path, monkeypatch, extra
):
    """미지원 Markdown 조합은 모델 로드·출력 생성·네트워크 차단 전 거부한다."""
    import sys

    from pdf_ocr import cli

    output = tmp_path / "new"
    monkeypatch.setattr(
        sys,
        "argv",
        ["ocr", "missing.pdf", "--format", "md", "--output", str(output), *extra],
    )
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert not output.exists()
