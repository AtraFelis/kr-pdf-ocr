"""Local desktop UI; OCR runs in a separate process to keep the screen responsive."""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import (
    QIODevice,
    QProcess,
    QProcessEnvironment,
    QSaveFile,
    Qt,
    QTimer,
)
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .devices import ocr_python
from .pdf import page_count, render_pages
from .preview import PagePreview
from .selection import Region, select_pages

ROOT = Path(__file__).resolve().parents[2]


def configure_application(app):
    app.setStyle("Fusion")
    # Fusion still inherits Windows colors. Keep the app's light backgrounds
    # and control/text colors in the same scheme, including inactive windows.
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    palette = app.style().standardPalette()
    colors = {
        QPalette.ColorRole.Window: "#f6f8fc",
        QPalette.ColorRole.WindowText: "#1e293b",
        QPalette.ColorRole.Base: "#ffffff",
        QPalette.ColorRole.AlternateBase: "#edf1f7",
        QPalette.ColorRole.Text: "#1e293b",
        QPalette.ColorRole.Button: "#eef2f8",
        QPalette.ColorRole.ButtonText: "#1e293b",
        QPalette.ColorRole.BrightText: "#ffffff",
        QPalette.ColorRole.PlaceholderText: "#64748b",
        QPalette.ColorRole.Highlight: "#315ceb",
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.Accent: "#315ceb",
        QPalette.ColorRole.Link: "#315ceb",
        QPalette.ColorRole.LinkVisited: "#6941a5",
        QPalette.ColorRole.ToolTipBase: "#ffffff",
        QPalette.ColorRole.ToolTipText: "#1e293b",
        QPalette.ColorRole.Light: "#ffffff",
        QPalette.ColorRole.Midlight: "#eef2f8",
        QPalette.ColorRole.Mid: "#cbd5e1",
        QPalette.ColorRole.Dark: "#94a3b8",
        QPalette.ColorRole.Shadow: "#64748b",
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#64748b"))
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor("#f1f5f9")
    )
    app.setPalette(palette)
    # The offscreen Qt backend does not discover Windows fonts automatically.
    # Register the installed font; do not distribute a copy of the font file.
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "malgun.ttf"
    family = "Malgun Gothic"
    if font_path.is_file():
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            family = families[0]
    app.setFont(QFont(family, 10))


class OCRWindow(QMainWindow):
    def __init__(self, root=ROOT):
        super().__init__()
        self.root = Path(root)
        self.pdf_path = None
        self.total = 0
        self.regions = {}
        self.preview_size = (1, 1)
        self.updating_pages = False
        self.cancelled = False
        self.closing_after_cancel = False
        self.run_folder = None
        self.log_buffer = ""
        self.completed = set()
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_process_output)
        self.process.finished.connect(self.process_finished)
        self.process.errorOccurred.connect(self.process_error)
        self.setWindowTitle("한국어 PDF OCR")
        self.resize(1380, 880)
        self.setAcceptDrops(True)
        self.build_ui()
        self.set_busy(False)

    def build_ui(self):
        body = QWidget()
        self.setCentralWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(20, 16, 20, 16)
        title = QLabel("한국어 PDF OCR")
        title.setStyleSheet("font-size: 23px; font-weight: 700;")
        layout.addWidget(title)
        layout.addWidget(
            QLabel("PDF를 로컬에서 읽고, 필요한 페이지와 영역만 TXT로 저장합니다.")
        )
        toolbar = QHBoxLayout()
        self.open_button = QPushButton("PDF 열기")
        self.open_button.clicked.connect(self.choose_pdf)
        toolbar.addWidget(self.open_button)
        self.file_label = QLabel("파일을 열거나 이 창으로 끌어오세요.")
        toolbar.addWidget(self.file_label, 1)
        self.run_button = QPushButton("OCR 실행")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.start_ocr)
        toolbar.addWidget(self.run_button)
        self.cancel_button = QPushButton("취소")
        self.cancel_button.clicked.connect(self.cancel_ocr)
        toolbar.addWidget(self.cancel_button)
        self.save_button = QPushButton("TXT 저장")
        self.save_button.clicked.connect(self.choose_save)
        toolbar.addWidget(self.save_button)
        layout.addLayout(toolbar)
        panels = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(panels, 1)

        self.sidebar = QWidget()
        self.sidebar.setMaximumWidth(280)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(0, 8, 12, 0)
        side.addWidget(QLabel("처리할 페이지"))
        self.pages_field = QLineEdit("all")
        self.pages_field.setPlaceholderText("예: 1,3,5-7 또는 all")
        self.exclude_field = QLineEdit()
        self.exclude_field.setPlaceholderText("제외할 페이지: 2,6-7")
        side.addWidget(self.pages_field)
        side.addWidget(self.exclude_field)
        apply_pages = QPushButton("페이지 범위 적용")
        apply_pages.clicked.connect(self.apply_page_fields)
        side.addWidget(apply_pages)
        self.page_list = QListWidget()
        self.page_list.currentRowChanged.connect(self.show_page)
        self.page_list.itemChanged.connect(self.page_checks_changed)
        side.addWidget(self.page_list, 1)
        side.addWidget(QLabel("인식 모델"))
        self.model = QComboBox()
        self.model.addItem("PP-OCRv5 한국어", "paddle")
        self.model.addItem("PaddleOCR-VL 1.6", "vl16")
        self.model.addItem("Qwen3-VL 2B", "qwen")
        side.addWidget(self.model)
        side.addWidget(QLabel("처리 장치"))
        self.device = QComboBox()
        self.device.addItem("CPU", "cpu")
        self.device.addItem("GPU · NVIDIA", "gpu")
        side.addWidget(self.device)
        self.device_notice = QLabel()
        self.device_notice.setWordWrap(True)
        self.device_notice.setStyleSheet(
            "background:#fff7e6;color:#684313;border:1px solid #efd8aa;"
            "border-radius:5px;padding:8px;"
        )
        side.addWidget(self.device_notice)
        self.device.currentIndexChanged.connect(self.update_device_notice)
        self.model.currentIndexChanged.connect(self.update_device_notice)
        self.update_device_notice()
        self.repair = QCheckBox("한국어 띄어쓰기 보정 제안")
        self.repair.setChecked(True)
        side.addWidget(self.repair)
        self.repair.setToolTip(
            "글자는 유지하며 공백만 보정합니다. 고유명사 등은 원문 확인이 필요합니다."
        )
        self.model.currentIndexChanged.connect(self.update_spacing_option)
        self.keep_hanja = QCheckBox("병기 한자 유지")
        side.addWidget(self.keep_hanja)
        panels.addWidget(self.sidebar)

        preview_panel = QWidget()
        middle = QVBoxLayout(preview_panel)
        middle.setContentsMargins(4, 8, 4, 0)
        top = QHBoxLayout()
        self.page_label = QLabel("PDF 미리보기")
        top.addWidget(self.page_label, 1)
        self.zoom = QComboBox()
        for value in (50, 75, 100, 125, 150, 200):
            self.zoom.addItem(f"{value}%", value / 100)
        self.zoom.setCurrentIndex(2)
        self.zoom.currentIndexChanged.connect(
            lambda: self.preview.set_zoom(self.zoom.currentData())
        )
        top.addWidget(self.zoom)
        middle.addLayout(top)
        middle.addWidget(QLabel("마우스로 드래그해 가져올 영역을 선택하세요."))
        self.preview = PagePreview()
        self.preview.region_changed.connect(self.selection_changed)
        scroll = QScrollArea()
        scroll.setObjectName("previewScroll")
        scroll.setWidget(self.preview)
        scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        middle.addWidget(scroll, 1)
        self.coordinate_label = QLabel("미리보기 기준 픽셀 좌표")
        middle.addWidget(self.coordinate_label)
        coordinates = QHBoxLayout()
        self.coordinates = []
        for label in ("왼쪽", "위쪽", "오른쪽", "아래쪽"):
            coordinates.addWidget(QLabel(label))
            field = QSpinBox()
            field.setRange(0, 100000)
            self.coordinates.append(field)
            coordinates.addWidget(field)
        middle.addLayout(coordinates)
        apply = QHBoxLayout()
        self.scope = QComboBox()
        self.scope.addItems(["현재 페이지", "체크한 페이지", "모든 페이지"])
        apply.addWidget(self.scope)
        self.apply_region_button = QPushButton("영역 적용")
        self.apply_region_button.clicked.connect(self.apply_region)
        apply.addWidget(self.apply_region_button)
        self.reset_region_button = QPushButton("전체 영역")
        self.reset_region_button.clicked.connect(lambda: self.apply_region(Region()))
        apply.addWidget(self.reset_region_button)
        middle.addLayout(apply)
        panels.addWidget(preview_panel)

        result_panel = QWidget()
        right = QVBoxLayout(result_panel)
        right.setContentsMargins(12, 8, 0, 0)
        right.addWidget(QLabel("추출 결과 · 선택 페이지 전체"))
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(
            "OCR이 끝나면 결과가 표시됩니다. 여기서 수정한 뒤 TXT로 저장하세요."
        )
        self.editor.textChanged.connect(self.update_save_button)
        right.addWidget(self.editor, 1)
        self.review_label = QLabel(
            "인식 오류와 띄어쓰기 제안은 원문과 비교해 확인해 주세요."
        )
        self.review_label.setWordWrap(True)
        right.addWidget(self.review_label)
        panels.addWidget(result_panel)
        panels.setSizes([230, 600, 480])
        bottom = QHBoxLayout()
        self.status = QLabel("PDF를 열어 시작하세요.")
        bottom.addWidget(self.status, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFixedWidth(240)
        bottom.addWidget(self.progress)
        layout.addLayout(bottom)
        self.setStyleSheet(
            "QMainWindow {background:#f6f8fc;} "
            "QPushButton {padding:7px 12px;} "
            "QPushButton#primary {background:#315ceb;color:white;border-radius:5px;} "
            "QPushButton#primary:disabled {background:#d8e0ec;color:#64748b;} "
            "QLineEdit,QSpinBox,QComboBox {padding:4px;} "
            "QPlainTextEdit,QListWidget {background:white;border:1px solid #d8e0ec;} "
            "QScrollArea#previewScroll {background:#edf1f7;border:1px solid #d8e0ec;} "
            "QProgressBar {min-height:18px;}"
        )

    def running(self):
        return self.process.state() != QProcess.ProcessState.NotRunning

    def set_busy(self, busy):
        editable_region = (
            not busy and self.pdf_path is not None and not self.preview.pixmap.isNull()
        )
        self.open_button.setEnabled(not busy)
        self.sidebar.setEnabled(not busy)
        self.preview.setEnabled(not busy)
        self.apply_region_button.setEnabled(editable_region)
        self.reset_region_button.setEnabled(editable_region)
        for field in self.coordinates:
            field.setEnabled(editable_region)
        self.run_button.setEnabled(not busy and self.pdf_path is not None)
        self.cancel_button.setEnabled(busy)
        self.editor.setReadOnly(busy)
        self.save_button.setEnabled(not busy and bool(self.editor.toPlainText()))

    def update_save_button(self):
        self.save_button.setEnabled(
            not self.running() and bool(self.editor.toPlainText())
        )

    def update_spacing_option(self):
        self.repair.setEnabled(self.model.currentData() == "paddle")
        self.repair.setToolTip(
            "기본 모델의 결과에서 공백만 보정합니다. 고유명사 등은 원문 확인이 필요합니다."
            if self.model.currentData() == "paddle"
            else "이 모델은 자체 문단 형태를 출력하므로 별도 띄어쓰기 보정을 적용하지 않습니다."
        )

    def update_device_notice(self):
        if self.device.currentData() == "cpu":
            text = (
                "CPU 사용 안내\nGPU보다 처리가 오래 걸릴 수 있으며, "
                "CPU 사용량이 늘어 다른 작업이 느려질 수 있습니다. "
                "CPU 선택 자체가 인식 정확도를 낮추는 것은 아닙니다."
            )
            if self.model.currentData() != "paddle":
                text += " 이 모델은 CPU에서 특히 느리고 메모리도 많이 사용합니다."
        else:
            text = (
                "GPU 사용 안내\nNVIDIA GPU와 모델에 맞는 GPU 실행 환경이 필요합니다. "
                "실행할 수 없다면 오류 안내를 확인하거나 CPU로 바꿔 주세요."
            )
        self.device_notice.setText(text)

    def confirm_discard(self):
        if not self.editor.document().isModified():
            return True
        return (
            QMessageBox.question(
                self,
                "편집한 결과",
                "저장하지 않은 수정 내용이 있습니다. 계속하면 화면의 수정 내용을 지웁니다. 계속할까요?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )

    def choose_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "PDF 열기", "", "PDF 파일 (*.pdf)")
        if path:
            self.load_pdf(Path(path))

    def load_pdf(self, path):
        if self.running() or not self.confirm_discard():
            return False
        try:
            total = page_count(path)
            if total < 1:
                raise ValueError("페이지가 없는 PDF입니다.")
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "PDF 열기 실패", str(error))
            return False
        self.pdf_path = Path(path).resolve()
        self.total = total
        self.regions = {}
        self.file_label.setText(f"{path.name} · {total}페이지")
        self.file_label.setToolTip(str(self.pdf_path))
        self.pages_field.setText("all")
        self.exclude_field.clear()
        self.updating_pages = True
        self.page_list.clear()
        for number in range(1, total + 1):
            item = QListWidgetItem(f"{number}페이지")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.page_list.addItem(item)
        self.updating_pages = False
        self.editor.clear()
        self.editor.document().setModified(False)
        self.page_list.setCurrentRow(0)
        self.status.setText("페이지와 영역을 선택한 뒤 OCR을 실행하세요.")
        self.set_busy(False)
        return True

    def checked_pages(self):
        return [
            index + 1
            for index in range(self.total)
            if self.page_list.item(index).checkState() == Qt.CheckState.Checked
        ]

    def page_checks_changed(self, item):
        if not self.updating_pages:
            self.pages_field.setText(",".join(map(str, self.checked_pages())))
            self.exclude_field.clear()

    def apply_page_fields(self):
        if self.pdf_path is None:
            return False
        try:
            if not self.pages_field.text().strip():
                raise ValueError("처리할 페이지를 체크하거나 범위를 입력하세요.")
            pages = select_pages(
                self.pages_field.text(), self.exclude_field.text(), self.total
            )
        except ValueError as error:
            QMessageBox.warning(self, "페이지 선택", str(error))
            return False
        self.updating_pages = True
        for index in range(self.total):
            self.page_list.item(index).setCheckState(
                Qt.CheckState.Checked if index + 1 in pages else Qt.CheckState.Unchecked
            )
        self.updating_pages = False
        return True

    def show_page(self, index):
        if self.pdf_path is None or index < 0:
            return
        self.preview.clear_image()
        try:
            # Preview DPI is separate from the OCR's 300 DPI; regions are normalized.
            for _, image in render_pages(self.pdf_path, [index + 1], 96):
                self.preview_size = image.size
                self.preview.set_image(image)
                image.close()
        except (ValueError, OSError, RuntimeError) as error:
            self.set_busy(self.running())
            QMessageBox.warning(self, "미리보기 실패", str(error))
            return
        self.page_label.setText(f"{index + 1} / {self.total}페이지")
        self.coordinate_label.setText(
            f"미리보기 기준 픽셀 좌표 · {self.preview_size[0]} × {self.preview_size[1]}"
        )
        self.set_current_region(self.regions.get(index + 1, Region()))
        self.set_busy(self.running())

    def set_current_region(self, region):
        self.preview.set_region(region)
        width, height = self.preview_size
        for field, limit, value in zip(
            self.coordinates,
            (width, height, width, height),
            region.values(),
            strict=True,
        ):
            field.setMaximum(limit)
            field.setValue(round(limit * value))

    def selection_changed(self, region):
        number = self.page_list.currentRow() + 1
        self.regions[number] = region
        self.set_current_region(region)

    def apply_region(self, region=None):
        if self.pdf_path is None:
            return
        # QPushButton.clicked passes a bool; it is not a region.
        if not isinstance(region, Region):
            try:
                region = Region.from_pixels(
                    [field.value() for field in self.coordinates], *self.preview_size
                )
            except ValueError as error:
                QMessageBox.warning(self, "영역 선택", str(error))
                return
        pages = (
            [self.page_list.currentRow() + 1]
            if self.scope.currentIndex() == 0
            else self.checked_pages()
            if self.scope.currentIndex() == 1
            else list(range(1, self.total + 1))
        )
        if not pages:
            QMessageBox.warning(self, "영역 선택", "적용할 페이지를 체크하세요.")
            return
        for number in pages:
            self.regions[number] = region
        self.set_current_region(
            self.regions.get(self.page_list.currentRow() + 1, Region())
        )
        self.status.setText(f"{len(pages)}개 페이지에 영역을 적용했습니다.")

    def start_ocr(self):
        if (
            self.running()
            or self.pdf_path is None
            or not self.apply_page_fields()
            or not self.confirm_discard()
        ):
            return
        pages = self.checked_pages()
        session = self.root / "output" / f"gui-{uuid4().hex[:12]}"
        try:
            session.mkdir(parents=True, exist_ok=False)
            settings = session / "regions.json"
            settings.write_text(
                json.dumps(
                    {str(k): v.values() for k, v in self.regions.items()}, indent=2
                ),
                encoding="utf-8",
            )
        except OSError as error:
            QMessageBox.warning(self, "작업 시작 실패", str(error))
            return
        self.run_folder = session / "result"
        args = [
            "-u",
            "-m",
            "pdf_ocr.cli",
            str(self.pdf_path),
            "--pages",
            ",".join(map(str, pages)),
            "--regions-file",
            str(settings),
            "--engine",
            self.model.currentData(),
            "--device",
            self.device.currentData(),
            "--output",
            str(self.run_folder),
        ]
        if self.repair.isChecked() and self.model.currentData() == "paddle":
            args.append("--repair-spacing")
        if self.keep_hanja.isChecked():
            args.append("--keep-hanja")
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONIOENCODING", "utf-8")
        self.process.setProcessEnvironment(environment)
        self.process.setWorkingDirectory(str(ROOT))
        self.cancelled = False
        self.completed = set()
        self.log_buffer = ""
        self.editor.clear()
        self.editor.document().setModified(False)
        self.progress.setRange(0, len(pages))
        self.progress.setValue(0)
        self.status.setText("인식 모델을 준비하고 있습니다…")
        self.set_busy(True)
        self.process.start(ocr_python(self.root, self.model.currentData()), args)

    def read_process_output(self):
        self.log_buffer += bytes(self.process.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )
        self.completed = set(
            map(int, re.findall(r"page=(\d+) lines=", self.log_buffer))
        )
        self.progress.setValue(len(self.completed))
        if self.completed:
            self.status.setText(
                f"{len(self.completed)} / {self.progress.maximum()}페이지 완료"
            )

    def cancel_ocr(self):
        if not self.running():
            return
        self.cancelled = True
        self.status.setText("취소 중입니다. 완료된 페이지의 결과는 보존합니다…")
        self.process.terminate()
        QTimer.singleShot(2000, self.kill_if_running)

    def kill_if_running(self):
        if self.cancelled and self.running():
            self.process.kill()

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.set_busy(False)
            self.status.setText("OCR 실행 환경을 시작하지 못했습니다.")
            QMessageBox.warning(
                self,
                "실행 실패",
                "프로젝트 가상환경에서 프로그램을 실행했는지 확인하세요.",
            )

    def process_finished(self, code, status):
        self.read_process_output()
        if self.run_folder is not None:
            try:
                (self.run_folder.parent / "process.log").write_text(
                    self.log_buffer, encoding="utf-8"
                )
                combined = self.run_folder / "combined.txt"
                if combined.exists():
                    self.editor.setPlainText(combined.read_text(encoding="utf-8"))
                    self.editor.document().setModified(False)
                reviews = 0
                for path in self.run_folder.glob("page-*.json"):
                    record = json.loads(path.read_text(encoding="utf-8"))
                    reviews += len((record.get("restoration") or {}).get("reviews", []))
                self.review_label.setText(
                    f"확인 항목 {reviews}개 · 인식 결과를 원문과 비교한 뒤 저장하세요."
                )
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, "결과 읽기 실패", str(error))
        self.set_busy(False)
        if self.cancelled:
            self.status.setText(
                f"취소됨 · 완료된 {len(self.completed)}페이지의 결과 보존"
            )
        elif code == 0 and status == QProcess.ExitStatus.NormalExit:
            self.status.setText("OCR 완료 · 결과를 확인하고 TXT로 저장하세요.")
        else:
            self.status.setText("OCR 중단 · 완료된 결과는 보존했습니다.")
            message = QMessageBox(self)
            message.setWindowTitle("OCR 실행 오류")
            message.setText(
                "OCR을 완료하지 못했습니다. 모델 설치 상태와 선택 영역을 확인하세요."
            )
            message.setDetailedText(self.log_buffer[-8000:])
            message.exec()
        if self.closing_after_cancel:
            self.close()

    def save_result(self, path, overwrite=False):
        path = Path(path)
        if path.suffix.lower() != ".txt" or (
            self.pdf_path and path.resolve() == self.pdf_path
        ):
            raise ValueError("결과는 원본 PDF와 다른 TXT 파일로 저장하세요.")
        if path.exists() and not overwrite:
            raise FileExistsError("기존 파일 덮어쓰기는 확인이 필요합니다.")
        file = QSaveFile(str(path))
        if not file.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(file.errorString())
        data = self.editor.toPlainText().encode("utf-8")
        if file.write(data) != len(data) or not file.commit():
            raise OSError(file.errorString())
        self.editor.document().setModified(False)
        self.status.setText(f"저장 완료 · {path.name}")

    def choose_save(self):
        default = (
            self.pdf_path.with_suffix(".txt") if self.pdf_path else Path("result.txt")
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "TXT 저장",
            str(default),
            "TXT 파일 (*.txt)",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not path:
            return
        target = Path(path).with_suffix(".txt")
        overwrite = False
        if target.exists():
            overwrite = (
                QMessageBox.question(
                    self,
                    "덮어쓰기 확인",
                    f"{target.name} 파일을 덮어쓸까요?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                == QMessageBox.StandardButton.Yes
            )
            if not overwrite:
                return
        try:
            self.save_result(target, overwrite)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "저장 실패", str(error))

    def dragEnterEvent(self, event):
        if (
            not self.running()
            and event.mimeData().hasUrls()
            and any(
                url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf")
                for url in event.mimeData().urls()
            )
        ):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf"):
                self.load_pdf(Path(url.toLocalFile()))
                break

    def closeEvent(self, event):
        if self.running():
            if (
                QMessageBox.question(
                    self,
                    "진행 중인 작업",
                    "OCR을 취소하고 창을 닫을까요?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                == QMessageBox.StandardButton.Yes
            ):
                self.closing_after_cancel = True
                self.cancel_ocr()
            event.ignore()
        elif self.confirm_discard():
            event.accept()
        else:
            event.ignore()


def main():
    parser = argparse.ArgumentParser(description="한국어 PDF OCR 데스크톱 화면")
    parser.add_argument("pdf", nargs="?", type=Path)
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    configure_application(app)
    window = OCRWindow()
    window.show()
    if args.pdf:
        window.load_pdf(args.pdf)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
