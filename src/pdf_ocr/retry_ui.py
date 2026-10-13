"""이미지 재인식 후보와 원문을 비교하고 사용자가 선택한 문장을 복사한다."""

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


class RetryDialog(QDialog):
    """원시 결과와 재인식 후보를 보여주며 편집 결과를 자동 교체하지 않는다."""

    def __init__(self, folder: Path, parent=None):
        """저장된 페이지별 후보를 읽고 원본 이미지 확인과 문장 복사 UI를 구성한다."""
        super().__init__(parent)
        self.folder = folder.resolve()
        self.items = []
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
            for retry in record.get("recognition_retry", []):
                for candidate in retry["candidates"]:
                    self.items.append((retry, candidate))
                    state = (
                        "인식 실패"
                        if candidate["state"] == "failed"
                        else candidate["text"] or "인식된 글자 없음"
                    )
                    self.list.addItem(
                        f"{record['page']}페이지 · {retry['line_index'] + 1}줄 · {candidate['scale']}배: {state}"
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
        if candidate["state"] == "failed":
            self.details.setPlainText(
                f"원시 인식: {retry['original']}\n재인식 실패: {candidate['error']}"
            )
        else:
            self.details.setPlainText(
                f"원시 인식: {retry['original']}\n재인식 후보: {candidate['text']}\n모델 점수: {candidate['confidence']:.3f}"
            )
            self.copy_button.setEnabled(bool(candidate["text"]))

    def copy_candidate(self):
        """선택한 성공 후보만 복사하며 현재 편집 내용이나 파일을 변경하지 않는다."""
        index = self.list.currentRow()
        if 0 <= index < len(self.items):
            candidate = self.items[index][1]
            if candidate["state"] == "completed" and candidate["text"]:
                QApplication.clipboard().setText(candidate["text"])
