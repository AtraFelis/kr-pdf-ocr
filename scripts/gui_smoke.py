"""Exercise the desktop's real OCR subprocess and save private local previews."""

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import QApplication

from pdf_ocr.gui import OCRWindow, configure_application
from pdf_ocr.selection import Region


def main():
    """첫 페이지의 선택 영역을 실제 GUI OCR로 처리하고 화면·저장 결과·실행 기록을 남긴다."""
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument(
        "--engine", default="paddle", choices=("paddle", "vl16", "qwen")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    app = QApplication([])
    configure_application(app)
    window = OCRWindow()
    window.show()
    if not window.load_pdf(args.pdf):
        raise RuntimeError("PDF 미리보기 실패")
    window.pages_field.setText("1")
    window.apply_page_fields()
    window.model.setCurrentIndex(window.model.findData(args.engine))
    window.apply_region(Region(0, 0.2, 1, 0.9))
    app.processEvents()
    window.grab().save(str(args.output / "before.png"))
    window.process.finished.connect(app.quit)
    QTimer.singleShot(90000, app.quit)
    window.start_ocr()
    app.exec()
    if window.process.state() != QProcess.ProcessState.NotRunning:
        window.process.kill()
        window.process.waitForFinished(10000)
        raise RuntimeError("OCR 실행 시간 초과")
    if window.process.exitCode() != 0 or not window.editor.toPlainText().strip():
        raise RuntimeError("화면을 통한 OCR 실행 실패")
    window.grab().save(str(args.output / "after.png"))
    target = args.output / "edited.txt"
    window.save_result(target)
    report = {
        "engine": args.engine,
        "completed_pages": sorted(window.completed),
        "result_directory": str(window.run_folder),
        "text_saved": target.exists(),
        "status": window.status.text(),
    }
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=True))
    window.close()


if __name__ == "__main__":
    main()
