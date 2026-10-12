"""고유명사 사전 관리와 편집본을 덮어쓰지 않는 재보정 비교 창을 제공한다."""

from pathlib import Path
from uuid import uuid4

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from .dictionary import (
    UserDictionary,
    import_words,
    load_dictionary,
    save_dictionary,
    write_local,
)


def confirm_replace(parent, path: Path) -> bool:
    """기존 파일 덮어쓰기의 승인을 받고 새 파일이면 즉시 허용한다."""
    return (
        not path.exists()
        or QMessageBox.question(
            parent,
            "덮어쓰기 확인",
            f"{path.name} 파일을 덮어쓸까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        == QMessageBox.StandardButton.Yes
    )


class DictionaryDialog(QDialog):
    """사전별 이름·단어 편집과 가져오기·내보내기·저장을 관리한다."""

    def __init__(self, folder: Path, selected=None, parent=None):
        """저장 위치와 선택 경로를 받으며 실제 저장 전까지 파일을 변경하지 않는다."""
        super().__init__(parent)
        self.folder = folder
        self.selected = Path(selected) if selected else None
        self.path = None
        self.clean = ("", "")
        self.loading = False
        self.setWindowTitle("고유명사 사전 관리")
        self.resize(680, 600)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "한 줄에 한 단어를 입력하세요. 단어 수정·삭제는 아래에서 할 수 있습니다."
            )
        )
        self.files = QListWidget()
        self.files.setMaximumHeight(100)
        self.files.currentRowChanged.connect(self.open_selected)
        layout.addWidget(self.files)
        self.name = QLineEdit()
        self.name.setPlaceholderText("사전 이름: 예시 작품")
        layout.addWidget(self.name)
        self.words = QPlainTextEdit()
        self.words.setPlaceholderText("하루카\n푸른별 연구소")
        layout.addWidget(self.words, 1)
        hint = QLabel(
            "중복은 정리하고 서로 다른 띄어쓰기 표기는 저장 전에 알려드립니다. 사전도 원문 대조가 필요합니다."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        actions = QHBoxLayout()
        for title, method in (
            ("새 사전", self.new_dictionary),
            ("TXT 가져오기", self.import_txt),
            ("TXT 내보내기", self.export_txt),
            ("사전 저장", self.save),
            ("사전 삭제", self.delete),
            ("닫기", self.close),
        ):
            button = QPushButton(title)
            button.clicked.connect(method)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.refresh(self.selected)

    def refresh(self, selected=None):
        """로컬 JSON 목록을 새로 읽고 선택 경로의 사전을 연다."""
        self.loading = True
        self.files.clear()
        self.paths = sorted(self.folder.glob("*.json"))
        for path in self.paths:
            try:
                dictionary = load_dictionary(path)
                title = f"{dictionary.name} · {len(dictionary.words)}개"
            except (OSError, ValueError, TypeError):
                title = f"{path.stem} · 파일 확인 필요"
            self.files.addItem(title)
        row = self.paths.index(selected) if selected in self.paths else -1
        self.files.setCurrentRow(row)
        self.loading = False
        if row >= 0:
            self.open_selected(row)

    def discard_allowed(self):
        """저장하지 않은 사전 변경을 버릴 때 확인한다."""
        return (
            self.clean == (self.name.text(), self.words.toPlainText())
            or QMessageBox.question(
                self,
                "사전 편집",
                "저장하지 않은 사전 변경을 버릴까요?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )

    def open_selected(self, row):
        """선택 사전을 검사해 열고 거부·실패 시 현재 편집을 보존한다."""
        if self.loading or row < 0:
            return
        previous = self.path
        try:
            if not self.discard_allowed():
                raise ValueError("현재 편집 유지")
            dictionary = load_dictionary(self.paths[row])
        except (OSError, ValueError, TypeError) as error:
            if str(error) != "현재 편집 유지":
                QMessageBox.warning(self, "사전 열기 실패", str(error))
            self.loading = True
            self.files.setCurrentRow(
                self.paths.index(previous) if previous in self.paths else -1
            )
            self.loading = False
            return
        self.path = self.paths[row]
        self.selected = self.path
        self.name.setText(dictionary.name)
        self.words.setPlainText("\n".join(dictionary.words))
        self.clean = (self.name.text(), self.words.toPlainText())

    def new_dictionary(self):
        """편집 폐기 승인 뒤 파일을 만들지 않고 새 사전 입력을 시작한다."""
        if self.discard_allowed():
            self.loading = True
            self.files.setCurrentRow(-1)
            self.loading = False
            self.path = None
            self.name.clear()
            self.words.clear()
            self.clean = ("", "")

    def current_dictionary(self):
        """현재 입력 전체를 검증해 불변 사전으로 반환한다."""
        return UserDictionary(self.name.text(), self.words.toPlainText().splitlines())

    def save(self):
        """새 파일 또는 승인된 기존 경로에 저장하며 실패 시 편집을 유지한다."""
        try:
            dictionary = self.current_dictionary()
            target = self.path or self.folder / f"dictionary-{uuid4().hex}.json"
            if not confirm_replace(self, target):
                return
            save_dictionary(target, dictionary, overwrite=self.path is not None)
            self.name.setText(dictionary.name)
            self.words.setPlainText("\n".join(dictionary.words))
            self.clean = (self.name.text(), self.words.toPlainText())
            self.path = self.selected = target
            self.refresh(target)
        except (ValueError, OSError, TypeError) as error:
            QMessageBox.warning(self, "사전 저장 실패", str(error))

    def import_txt(self):
        """TXT 단어를 현재 목록에 병합하고 잘못된 입력이면 기존 내용을 보존한다."""
        path, _ = QFileDialog.getOpenFileName(
            self, "단어 TXT 가져오기", "", "TXT (*.txt)"
        )
        if not path:
            return
        try:
            words = import_words(Path(path))
            dictionary = UserDictionary(
                self.name.text() or Path(path).stem,
                self.words.toPlainText().splitlines() + list(words),
            )
            self.name.setText(dictionary.name)
            self.words.setPlainText("\n".join(dictionary.words))
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, "가져오기 실패", str(error))

    def export_txt(self):
        """검사한 단어 목록을 사용자가 고른 TXT에 저장하며 덮어쓰기를 확인한다."""
        try:
            dictionary = self.current_dictionary()
            path, _ = QFileDialog.getSaveFileName(
                self,
                "단어 TXT 내보내기",
                "dictionary.txt",
                "TXT (*.txt)",
                options=QFileDialog.Option.DontConfirmOverwrite,
            )
            if path:
                target = Path(path).with_suffix(".txt")
                if confirm_replace(self, target):
                    write_local(
                        target, "\n".join(dictionary.words) + "\n", target.exists()
                    )
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, "내보내기 실패", str(error))

    def delete(self):
        """선택한 사전의 삭제와 미저장 편집 폐기를 승인받아 파일을 삭제한다."""
        if self.path is None or not self.discard_allowed():
            return
        if (
            QMessageBox.question(
                self,
                "사전 삭제",
                "이 사전 파일을 삭제할까요?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self.path.unlink()
            self.path = self.selected = None
            self.name.clear()
            self.words.clear()
            self.clean = ("", "")
            self.refresh()
        except OSError as error:
            QMessageBox.warning(self, "삭제 실패", str(error))

    def closeEvent(self, event):
        """미저장 사전 편집을 확인한 뒤 창을 닫는다."""
        if self.discard_allowed():
            event.accept()
        else:
            event.ignore()

    def reject(self):
        """Escape로 닫을 때도 미저장 편집을 확인한다."""
        if self.discard_allowed():
            super().reject()


class ComparisonDialog(QDialog):
    """재보정의 원문·사전 미적용·적용 결과를 현재 편집본과 분리해 보여준다."""

    def __init__(self, folder: Path, parent=None):
        """디스크의 완료 결과를 읽기 전용으로 표시하고 출력 위치를 안내한다."""
        super().__init__(parent)
        self.setWindowTitle("사전 적용 전후 비교")
        self.folder = folder
        self.resize(1150, 650)
        layout = QVBoxLayout(self)
        label = QLabel(f"현재 편집 내용은 유지됩니다. 별도 결과 저장 위치: {folder}")
        label.setWordWrap(True)
        layout.addWidget(label)
        identity = (
            load_dictionary(folder / "dictionary.json").identity()
            if (folder / "dictionary.json").exists()
            else None
        )
        details = QLabel(
            f"적용 사전: {identity['name']} · {identity['word_count']}개 · {identity['sha256'][:12]}"
            if identity
            else "사용자 사전 미선택 · 기본 Kiwi 보정 결과입니다."
        )
        layout.addWidget(details)
        columns = QHBoxLayout()
        for title, name in (
            ("공백 보정 전", "before-spacing.txt"),
            ("사전 없이 Kiwi 보정", "without-dictionary.txt"),
            ("선택 사전으로 Kiwi 보정", "combined.txt"),
        ):
            column = QVBoxLayout()
            column.addWidget(QLabel(title))
            editor = QPlainTextEdit()
            editor.setReadOnly(True)
            editor.setPlainText((folder / name).read_text(encoding="utf-8"))
            column.addWidget(editor)
            columns.addLayout(column)
        layout.addLayout(columns, 1)
        save = QPushButton("재보정 결과 TXT 저장")
        save.clicked.connect(self.save_result)
        layout.addWidget(save)
        close = QPushButton("닫기")
        close.clicked.connect(self.accept)
        layout.addWidget(close)

    def save_result(self):
        """별도 재보정 결과를 TXT로 내보내며 기존 파일 덮어쓰기는 확인한다."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "재보정 결과 TXT 저장",
            "dictionary-result.txt",
            "TXT (*.txt)",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not path:
            return
        target = Path(path).with_suffix(".txt")
        if not confirm_replace(self, target):
            return
        try:
            text = (self.folder / "combined.txt").read_text(encoding="utf-8")
            write_local(target, text, overwrite=target.exists())
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "재보정 저장 실패", str(error))
