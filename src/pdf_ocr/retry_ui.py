"""이미지 재인식 후보와 원문을 비교하고 사용자가 선택한 문장을 복사한다."""

import json
import re
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from .retry import retry_reason


class RetryDialog(QDialog):
    """원시 결과와 재인식 후보를 보여주며 편집 결과를 자동 교체하지 않는다."""

    def __init__(self, folder: Path, parent=None):
        """저장된 페이지별 후보를 읽고 원본 이미지 확인과 문장 복사 UI를 구성한다."""
        super().__init__(parent)
        self.folder = folder.resolve()
        self.items = []
        self.page_paths = []
        self.closing = False
        self.process = QProcess(self)
        self.process.finished.connect(self.visual_finished)
        self.process.errorOccurred.connect(self.visual_error)
        self.setWindowTitle("짧은 대사·문장부호 재인식 비교")
        self.resize(850, 600)
        layout = QVBoxLayout(self)
        notice = QLabel(
            "원본 이미지를 확인하고 사용할 후보를 복사해 원문 편집에 붙여 넣으세요. 결과는 자동 변경되지 않습니다. 점수는 정확도 확률이 아닙니다."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.list = QListWidget()
        for path in sorted(folder.glob("page-*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            retries = list(record.get("recognition_retry", []))
            present = {item["line_index"] for item in retries}
            for index, line in enumerate(record.get("lines", [])):
                if index not in present and retry_reason(line) and line.get("polygon"):
                    retries.append(
                        {
                            "line_index": index,
                            "original": line["text"],
                            "candidates": [],
                        }
                    )
            for retry in retries:
                if not retry["candidates"]:
                    retry = {
                        **retry,
                        "candidates": [
                            {
                                "state": "original",
                                "text": retry["original"],
                                "scale": 1,
                                "confidence": None,
                            }
                        ],
                    }
                for candidate in retry["candidates"]:
                    self.items.append((retry, candidate))
                    self.page_paths.append(path)
                    state = (
                        "인식 실패"
                        if candidate["state"] == "failed"
                        else candidate["text"] or "인식된 글자 없음"
                    )
                    self.list.addItem(
                        f"{record['page']}페이지 · {retry['line_index'] + 1}줄 · {candidate.get('model', str(candidate['scale']) + '배')}: {state}"
                    )
        layout.addWidget(self.list)
        self.image = QLabel()
        layout.addWidget(self.image)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        layout.addWidget(self.details)
        self.copy_button = QPushButton("선택 후보 문장 복사")
        self.copy_button.clicked.connect(self.copy_candidate)
        layout.addWidget(self.copy_button)
        self.apply_button = QPushButton("선택 후보를 편집기에 반영")
        self.apply_button.clicked.connect(self.apply_candidate)
        layout.addWidget(self.apply_button)
        self.model_choice = QComboBox()
        self.model_choice.addItem("VL 1.6으로 선택 영역 다시 읽기", "PaddleOCR-VL-1.6")
        self.model_choice.addItem(
            "Qwen으로 선택 영역 다시 읽기", "Qwen3-VL-2B-Instruct"
        )
        layout.addWidget(self.model_choice)
        self.visual_button = QPushButton("선택 영역을 다른 로컬 모델로 재인식")
        self.visual_button.clicked.connect(self.start_visual)
        layout.addWidget(self.visual_button)
        self.visual_notice = QLabel(
            "모델별로 틀릴 수 있습니다. 글자·말줄임표·마침표를 이미지와 비교한 뒤 반영하세요."
        )
        self.visual_notice.setWordWrap(True)
        layout.addWidget(self.visual_notice)
        close = QPushButton("닫기")
        close.clicked.connect(self.accept)
        layout.addWidget(close)
        self.list.currentRowChanged.connect(self.show_candidate)
        self.show_candidate(-1)
        if self.items:
            self.list.setCurrentRow(0)

    def show_candidate(self, index):
        """선택한 후보의 실제 이미지·원문·점수·실패 이유를 표시한다."""
        self.image.clear()
        self.copy_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        self.visual_button.setEnabled(
            0 <= index < len(self.items)
            and self.process.state() == QProcess.ProcessState.NotRunning
        )
        if not 0 <= index < len(self.items):
            self.details.setPlainText(
                "재인식 후보가 없습니다. PP-OCRv5 TXT에서 재인식 옵션을 켜고 실행하세요."
            )
            return
        retry, candidate = self.items[index]
        image = (self.folder / candidate.get("image", "")).resolve()
        if (
            image.is_relative_to(self.folder / "retry")
            and image.is_file()
            and image.suffix.lower() == ".png"
        ):
            self.image.setPixmap(
                QPixmap(str(image)).scaled(
                    780,
                    160,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        elif candidate["state"] == "original":
            page = json.loads(self.page_paths[index].read_text(encoding="utf-8"))
            polygon = page["lines"][retry["line_index"]].get("polygon")
            if polygon:
                xs, ys = zip(*polygon, strict=True)
                pixmap = QPixmap(str(self.page_paths[index].with_suffix(".png")))
                left, top = max(0, int(min(xs)) - 12), max(0, int(min(ys)) - 12)
                if not pixmap.isNull():
                    crop = pixmap.copy(
                        left,
                        top,
                        min(pixmap.width() - left, int(max(xs)) - left + 12),
                        min(pixmap.height() - top, int(max(ys)) - top + 12),
                    )
                    self.image.setPixmap(
                        crop.scaled(
                            780,
                            160,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
        if candidate["state"] == "failed":
            self.details.setPlainText(
                f"원시 인식: {retry['original']}\n재인식 실패: {candidate['error']}"
            )
        else:
            score = candidate.get("confidence")
            self.details.setPlainText(
                f"원시 인식: {retry['original']}\n재인식 후보: {candidate['text']}\n모델 점수: {score:.3f}"
                if score is not None
                else f"원시 인식: {retry['original']}\n후보: {candidate['text']}\n모델 점수: 미제공"
            )
            self.copy_button.setEnabled(
                candidate["state"] == "completed" and bool(candidate["text"])
            )
            self.apply_button.setEnabled(
                candidate["state"] == "completed"
                and bool(candidate["text"])
                and hasattr(self.parent(), "editor")
            )

    def copy_candidate(self):
        """선택한 성공 후보만 복사하며 현재 편집 내용이나 파일을 변경하지 않는다."""
        index = self.list.currentRow()
        if 0 <= index < len(self.items):
            candidate = self.items[index][1]
            if candidate["state"] == "completed" and candidate["text"]:
                QApplication.clipboard().setText(candidate["text"])

    def apply_candidate(self):
        """현재 편집기에 유일하게 일치하는 원시 구간만 사용자가 선택한 후보로 바꾼다."""
        index = self.list.currentRow()
        if not 0 <= index < len(self.items) or not hasattr(self.parent(), "editor"):
            return
        original, candidate = self.items[index]
        if candidate["state"] != "completed" or not candidate["text"]:
            return
        compact = re.sub(r"\s", "", original["original"])
        if not compact:
            return
        editor = self.parent().editor
        pattern = r"[ \t]*".join(re.escape(char) for char in compact)
        if compact[0].isascii() and compact[0].isalnum():
            pattern = r"(?<![A-Za-z0-9])" + pattern
        if compact[-1].isascii() and compact[-1].isalnum():
            pattern += r"(?![A-Za-z0-9])"
        matches = list(re.finditer(pattern, editor.toPlainText()))
        if len(matches) != 1:
            self.visual_notice.setText(
                "일치 구간이 없거나 여러 곳입니다. 후보를 복사해 원문과 비교하며 직접 수정하세요."
            )
            return
        text = editor.toPlainText()
        match = matches[0]
        cursor = editor.textCursor()
        cursor.beginEditBlock()
        cursor.setPosition(len(text[: match.start()].encode("utf-16-le")) // 2)
        cursor.setPosition(
            len(text[: match.end()].encode("utf-16-le")) // 2,
            cursor.MoveMode.KeepAnchor,
        )
        cursor.insertText(candidate["text"])
        cursor.endEditBlock()
        self.visual_notice.setText(
            "선택 후보를 편집기에 반영했습니다. 파일 저장은 별도로 진행하세요. 실행 취소로 되돌릴 수 있습니다."
        )

    def start_visual(self):
        """선택 줄의 VLM 재인식을 별도 프로세스에서 실행해 화면과 기존 편집을 유지한다."""
        index = self.list.currentRow()
        if (
            not 0 <= index < len(self.items)
            or self.process.state() != QProcess.ProcessState.NotRunning
        ):
            return
        root = Path(__file__).resolve().parents[2]
        python = root / ".venv/Scripts/python.exe"
        if not python.is_file():
            self.visual_notice.setText("VLM 실행 환경 .venv를 확인하세요.")
            return
        self.visual_index = index
        device = "cpu"
        parent = self.parent()
        if hasattr(parent, "device"):
            device = parent.device.currentData()
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONIOENCODING", "utf-8")
        self.process.setProcessEnvironment(environment)
        self.process.setWorkingDirectory(str(root))
        self.visual_button.setEnabled(False)
        self.visual_notice.setText(
            "선택 영역을 로컬 모델로 다시 읽는 중입니다. CPU에서는 오래 걸릴 수 있습니다."
        )
        self.process.start(
            str(python),
            [
                "-u",
                "-m",
                "pdf_ocr.retry_vl",
                str(self.page_paths[index]),
                str(self.items[index][0]["line_index"]),
                "--model",
                self.model_choice.currentData(),
                "--device",
                device,
            ],
        )

    def visual_error(self, error):
        """프로세스 시작 실패를 알리고 원래 후보와 편집 내용을 유지한다."""
        if error == QProcess.ProcessError.FailedToStart:
            self.visual_notice.setText(
                "재인식 프로세스를 시작하지 못했습니다. 로컬 환경을 확인하세요."
            )
            self.visual_button.setEnabled(True)

    def visual_finished(self, code, status):
        """성공한 저장 후보만 비교 목록에 추가하고 실패 시 로그를 안내한다."""
        if self.closing:
            return
        self.visual_button.setEnabled(True)
        if code != 0 or status != QProcess.ExitStatus.NormalExit:
            self.visual_notice.setText(
                "다른 모델 재인식에 실패했습니다. 기존 결과는 유지됩니다."
            )
            QMessageBox.warning(
                self,
                "재인식 실패",
                bytes(self.process.readAllStandardError()).decode(
                    "utf-8", errors="replace"
                )[-1200:],
            )
            return
        try:
            path = self.page_paths[self.visual_index]
            record = json.loads(path.read_text(encoding="utf-8"))
            index = self.items[self.visual_index][0]["line_index"]
            item = next(
                i for i in record["recognition_retry"] if i["line_index"] == index
            )
            candidate = item["candidates"][-1]
            self.items.append((item, candidate))
            self.page_paths.append(path)
            self.list.addItem(
                f"{record['page']}페이지 · {index + 1}줄 · {candidate['model']}: {candidate['text']}"
            )
            self.list.setCurrentRow(len(self.items) - 1)
            self.visual_notice.setText(
                "후보를 추가했습니다. 이미지에서 글자와 문장부호를 확인한 뒤 반영하세요."
            )
        except (OSError, ValueError, KeyError, StopIteration) as error:
            self.visual_notice.setText(f"후보 읽기에 실패했습니다: {error}")

    def done(self, result):
        """닫기·Escape·창 종료 시 소유한 재인식 프로세스만 중단하고 결과를 보존한다."""
        self.closing = True
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(3000)
        super().done(result)
