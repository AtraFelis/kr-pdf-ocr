"""Markdown 결과와 로컬 이미지를 원본 보호 조건에 따라 함께 내보낸다."""

import re
import shutil
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from PySide6.QtCore import QIODevice, QSaveFile, QUrl
from PySide6.QtGui import QImage, QTextDocument
from PySide6.QtWidgets import QTextBrowser


def save_markdown(path: Path, text: str, source: Path | None, overwrite=False):
    """참조 이미지를 새 폴더에 복사하고 승인된 Markdown 파일만 원자적으로 저장한다.

    기존 이미지 폴더는 변경하지 않는다. 실패 시 새로 복사된 파일이 남을 수
    있지만 기존 문서·이미지는 보존한다. 출력 이미지 링크는 상대 경로로 쓴다.
    """
    if path.suffix.lower() != ".md":
        raise ValueError("Markdown 결과는 .md 파일로 저장하세요.")
    if path.exists() and not overwrite:
        raise FileExistsError("기존 Markdown 덮어쓰기를 확인하세요.")
    references = sorted(set(re.findall(r"assets/[A-Za-z0-9_./-]+", text)))
    if references:
        if source is None:
            raise ValueError("Markdown 이미지가 있는 원래 결과 폴더가 필요합니다.")
        assets_root = (source / "assets").resolve()
        if not assets_root.is_relative_to(source.resolve()):
            raise ValueError(
                "결과 폴더 밖을 가리키는 이미지 폴더는 사용할 수 없습니다."
            )
        files = []
        for reference in references:
            image = (source / reference).resolve()
            if not image.is_relative_to(assets_root) or not image.is_file():
                raise ValueError(f"로컬 결과 이미지 경로를 확인하세요: {reference}")
            files.append((reference, image))
        target = path.parent / f"{path.stem}_assets-{uuid4().hex[:12]}"
        target.mkdir(exist_ok=False)
        replacements = {}
        for index, (reference, image) in enumerate(files, 1):
            name = f"image-{index:03}{image.suffix.lower()}"
            shutil.copyfile(image, target / name)
            replacements[reference] = f"{quote(target.name, safe='')}/{name}"
        text = re.sub(
            r"assets/[A-Za-z0-9_./-]+", lambda match: replacements[match.group()], text
        )
    file = QSaveFile(str(path))
    if not file.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError(file.errorString())
    data = text.encode("utf-8")
    if file.write(data) != len(data) or not file.commit():
        raise OSError(file.errorString())


class LocalMarkdownDocument(QTextDocument):
    """사용자 지정 문서에서도 Qt의 자원 읽기를 미리보기의 로컬 정책으로 제한한다."""

    def __init__(self, preview):
        """자원 정책을 소유한 미리보기와 문서 수명을 연결한다."""
        super().__init__(preview)
        self.preview = preview

    def loadResource(self, resource_type, name):
        """기본 파일·URL 로더 대신 허용된 로컬 이미지 로더에 위임한다."""
        return self.preview.loadResource(resource_type, name)


class MarkdownPreview(QTextBrowser):
    """결과 폴더 내부의 로컬 이미지만 읽으며 네트워크·링크 이동을 하지 않는 미리보기다."""

    def __init__(self, parent=None):
        """로컬 이미지 허용 범위와 링크 이동 금지를 설정한다."""
        super().__init__(parent)
        self.root = None
        self.image_limits = {}
        self.source_text = None
        self.displaying = False
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)

    def display(self, text: str, root: Path | None):
        """편집한 Markdown을 표시하고 이미지 검색 범위를 해당 결과 폴더로 제한한다."""
        self.displaying = True
        self.source_text = text
        self.root = root.resolve() if root else None
        self.image_limits = {}
        available_width = max(1, self.viewport().width() - 24)

        def image_preview(match):
            """공식 HTML 그림 컨테이너를 독립 문단으로 바꾸고 백분율 너비를 기록한다."""
            tag = match.group(1)
            source = re.search(r"""src\s*=\s*["']([^"']+)["']""", tag, re.IGNORECASE)
            if source is None:
                return match.group()
            path = source.group(1)
            percentage = re.search(
                r"""width\s*=\s*["']?(\d+(?:\.\d+)?)%""", tag, re.IGNORECASE
            )
            if percentage:
                limit = max(
                    1,
                    round(available_width * min(float(percentage.group(1)), 100) / 100),
                )
                self.image_limits[path] = limit
            return f"\n\n![Image]({path})\n\n"

        preview_text = re.sub(
            r"<div\b[^>]*>\s*(<img\b[^>]*>)\s*</div>",
            image_preview,
            text,
            flags=re.IGNORECASE,
        )
        previous_document = self.document()
        previous_owned = previous_document.parent() is self
        document = LocalMarkdownDocument(self)
        document.setDefaultFont(self.font())
        document.setBaseUrl(
            QUrl.fromLocalFile(str(self.root) + "/") if self.root else QUrl()
        )
        self.setDocument(document)
        if previous_owned:
            previous_document.deleteLater()
        self.setMarkdown(preview_text)
        self.displaying = False

    def resizeEvent(self, event):
        """폭 변경 시 그림 크기를 다시 계산하고 미리보기의 스크롤 위치를 유지한다."""
        super().resizeEvent(event)
        if getattr(self, "source_text", None) is not None and not self.displaying:
            position = self.verticalScrollBar().value()
            self.display(self.source_text, self.root)
            self.verticalScrollBar().setValue(position)

    def loadResource(self, resource_type, name):
        """외부 URL·결과 밖 파일을 거부하고 내부 이미지 자원만 읽는다."""
        if (
            resource_type != QTextDocument.ResourceType.ImageResource
            or self.root is None
        ):
            return None
        resolved = self.document().baseUrl().resolved(name)
        if not resolved.isLocalFile():
            return None
        path = Path(resolved.toLocalFile()).resolve()
        if (
            not path.is_relative_to(self.root / "assets")
            or not path.is_file()
            or path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".bmp")
        ):
            return None
        image = QImage(str(path))
        if image.isNull():
            return None
        if image is not None and hasattr(image, "width"):
            relative = path.relative_to(self.root).as_posix()
            limit = min(
                max(1, self.viewport().width() - 24),
                self.image_limits.get(relative, image.width()),
            )
            if image.width() > limit:
                image = image.scaledToWidth(limit)
        return image
