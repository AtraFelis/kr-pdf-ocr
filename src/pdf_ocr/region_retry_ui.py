"""누락된 줄도 포함하는 임의 PDF 영역을 별도 프로세스로 읽고 후보를 비교한다."""

import json
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from .devices import ocr_python
from .model_info import MODEL_GUIDES

ROOT = Path(__file__).resolve().parents[2]


class RegionRetryDialog(QDialog):
    """전체 페이지 상대 영역을 새 OCR 작업으로 읽고 명시적인 후보 삽입만 제공한다."""

    def __init__(
        self, root, pdf, page, region, dpi, device, threshold, model, parent=None
    ):
        """원본·페이지·선택 영역을 고정하고 실행·취소·비교·복사/삽입 화면을 만든다.

        원시 OCR 줄 목록을 수정하지 않으며 선택은 기존 추출 영역과 독립적이다.
        매 실행의 출력 폴더를 새로 만들고 창이 소유한 프로세스만 종료한다.
        """
        super().__init__(parent)
        self.root, self.pdf = Path(root), Path(pdf)
        self.page, self.region, self.threshold = page, region, threshold
        self.candidates = []
        self.closing = self.cancelled = False
        self.active_folder = None
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.process_finished)
        self.process.errorOccurred.connect(self.process_error)
        self.log = ""
        self.setWindowTitle(f"{page}페이지 · 임의 영역 재인식")
        self.resize(800, 650)
        layout = QVBoxLayout(self)
        notice = QLabel(
            "같은 선택 영역을 모델·DPI별로 읽고 후보를 비교합니다. 복사하거나 편집기 커서 위치에 삽입하세요. 원본 결과는 자동 변경되지 않습니다."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        controls = QHBoxLayout()
        self.model = QComboBox()
        for engine, guide in MODEL_GUIDES.items():
            self.model.addItem(guide["name"], engine)
        self.model.setCurrentIndex(max(0, self.model.findData(model)))
        controls.addWidget(self.model)
        self.dpi = QComboBox()
        for value in (200, 300, 400, 600):
            self.dpi.addItem(f"{value} DPI", value)
        self.dpi.setCurrentIndex(self.dpi.findData(dpi))
        controls.addWidget(self.dpi)
        self.device = QComboBox()
        self.device.addItem("CPU", "cpu")
        self.device.addItem("GPU", "gpu")
        self.device.setCurrentIndex(self.device.findData(device))
        controls.addWidget(self.device)
        layout.addLayout(controls)
        self.run_button = QPushButton("선택 영역 다시 읽기")
        self.run_button.clicked.connect(self.start)
        layout.addWidget(self.run_button)
        self.cancel_button = QPushButton("재인식 취소")
        self.cancel_button.clicked.connect(self.cancel)
        layout.addWidget(self.cancel_button)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.show_candidate)
        layout.addWidget(self.list)
        self.image = QLabel()
        layout.addWidget(self.image)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text)
        self.copy_button = QPushButton("후보 복사")
        self.copy_button.clicked.connect(self.copy_candidate)
        layout.addWidget(self.copy_button)
        self.insert_button = QPushButton("편집기 커서 위치에 삽입")
        self.insert_button.clicked.connect(self.insert_candidate)
        layout.addWidget(self.insert_button)
        self.status = QLabel(
            "모델과 처리 장치를 확인한 뒤 실행하세요. CPU는 오래 걸리고 자원을 많이 사용할 수 있습니다."
        )
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        close = QPushButton("닫기")
        close.clicked.connect(self.accept)
        layout.addWidget(close)
        self.set_busy(False)

    def set_busy(self, busy):
        """실행 설정을 잠그고 유효한 완료 후보가 있을 때만 복사·삽입을 허용한다."""
        for widget in (self.model, self.device, self.dpi, self.run_button):
            widget.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        selected = not busy and 0 <= self.list.currentRow() < len(self.candidates)
        self.copy_button.setEnabled(selected)
        parent = self.parent()
        self.insert_button.setEnabled(
            selected
            and parent is not None
            and getattr(parent, "result_format", "txt") == "txt"
            and hasattr(parent, "editor")
            and not parent.editor.isReadOnly()
        )

    def start(self):
        """고정된 PDF·상대 영역을 기존 CLI로 실행하고 매번 새 출력 경로를 사용한다."""
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return
        engine = self.model.currentData()
        try:
            executable = ocr_python(self.root, engine, "txt")
            session = self.root / "output" / f"region-retry-{uuid4().hex[:12]}"
            session.mkdir(parents=True, exist_ok=False)
        except (OSError, ValueError) as error:
            self.status.setText(f"시작하지 못했습니다: {error}")
            return
        self.active_folder = session / "result"
        self.active_model, self.active_dpi = engine, self.dpi.currentData()
        self.active_device = self.device.currentData()
        self.log = ""
        self.cancelled = False
        args = [
            "-u",
            "-m",
            "pdf_ocr.cli",
            str(self.pdf),
            "--pages",
            str(self.page),
            "--region",
            ",".join(map(str, self.region.values())),
            "--dpi",
            str(self.active_dpi),
            "--engine",
            engine,
            "--device",
            self.device.currentData(),
            "--keep-line-breaks",
            "--output",
            str(self.active_folder),
        ]
        if engine == "paddle":
            args.extend(["--det-box-thresh", str(self.threshold)])
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONIOENCODING", "utf-8")
        self.process.setProcessEnvironment(environment)
        self.process.setWorkingDirectory(str(ROOT))
        self.set_busy(True)
        self.status.setText("선택한 영역을 읽고 있습니다…")
        self.process.start(executable, args)

    def read_output(self):
        """작업 출력 로그를 UTF-8로 모아 실패 원인과 별도 기록에 사용한다."""
        self.log += bytes(self.process.readAllStandardOutput()).decode(
            "utf-8", "replace"
        )

    def process_finished(self, code, status):
        """정상 완료의 원시 TXT·이미지만 후보에 추가하고 취소·실패는 구분한다."""
        self.read_output()
        if self.closing:
            return
        self.set_busy(False)
        try:
            (self.active_folder.parent / "process.log").write_text(
                self.log, encoding="utf-8"
            )
            if self.cancelled:
                self.status.setText(
                    "재인식 취소 · 이전 후보와 저장된 부분 결과는 보존했습니다."
                )
                return
            if code != 0 or status != QProcess.ExitStatus.NormalExit:
                raise ValueError(self.log[-1500:] or "작업이 정상 완료되지 않았습니다.")
            path = self.active_folder / f"page-{self.page:03}.json"
            record = json.loads(path.read_text(encoding="utf-8"))
            if any(line.get("token_limit_reached") for line in record["lines"]):
                raise ValueError(
                    "결과가 토큰 상한으로 잘렸습니다. 더 작은 영역을 선택하세요."
                )
            text = "\n".join(line["text"] for line in record["lines"]).strip()
            if not text:
                raise ValueError(
                    "글자를 인식하지 못했습니다. 영역·모델·DPI를 확인하세요."
                )
            self.candidates.append({"text": text, "folder": self.active_folder})
            self.list.addItem(
                f"{MODEL_GUIDES[self.active_model]['name']} · {self.active_device.upper()} · "
                f"{self.active_dpi} DPI · {len(self.candidates)}번째 후보"
            )
            self.list.setCurrentRow(len(self.candidates) - 1)
            self.status.setText(
                "원본 이미지와 후보를 비교한 뒤 복사하거나 커서 위치에 삽입하세요."
            )
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.status.setText(f"재인식 실패: {error}")
        self.set_busy(False)

    def process_error(self, error):
        """프로세스 시작 실패를 알리고 기존 후보와 편집 내용을 유지한다."""
        if error == QProcess.ProcessError.FailedToStart:
            self.set_busy(False)
            self.status.setText(
                "재인식 프로세스를 시작하지 못했습니다. 실행 환경을 확인하세요."
            )

    def show_candidate(self, index):
        """선택한 완료 후보의 실제 입력 이미지와 원시 글자만 표시한다."""
        self.text.clear()
        self.image.clear()
        if 0 <= index < len(self.candidates):
            candidate = self.candidates[index]
            self.text.setPlainText(candidate["text"])
            image = QPixmap(str(candidate["folder"] / f"page-{self.page:03}-input.png"))
            self.image.setPixmap(
                image.scaled(
                    700,
                    180,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        self.set_busy(self.process.state() != QProcess.ProcessState.NotRunning)

    def copy_candidate(self):
        """사용자가 선택한 후보를 클립보드에 복사하며 기존 파일은 수정하지 않는다."""
        if self.copy_button.isEnabled():
            QApplication.clipboard().setText(self.text.toPlainText())

    def insert_candidate(self):
        """선택 후보를 현재 커서에 삽입하고 선택된 기존 텍스트를 덮어쓰지 않는다."""
        if not self.insert_button.isEnabled():
            return
        cursor = self.parent().editor.textCursor()
        cursor.clearSelection()
        cursor.beginEditBlock()
        cursor.insertText(self.text.toPlainText())
        cursor.endEditBlock()
        self.parent().editor.setTextCursor(cursor)
        self.status.setText(
            "커서 위치에 삽입했습니다. 실행 취소가 가능하며 파일 저장은 별도로 진행하세요."
        )

    def cancel(self):
        """소유한 실행만 중단하고 완료된 후보 및 다른 작업 결과는 보존한다."""
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.cancelled = True
            self.process.kill()

    def done(self, result):
        """창 종료·Escape 시 재인식 프로세스를 중단하고 원본·편집본을 유지한다."""
        self.closing = True
        self.cancel()
        self.process.waitForFinished(3000)
        super().done(result)
