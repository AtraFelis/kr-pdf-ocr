"""선택 모델의 문서·출력 권장과 실제 앱 지원 범위를 한곳에서 관리한다."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

MODEL_GUIDES = {
    "paddle": {
        "name": "PP-OCRv5 한국어",
        "documents": "소설·일반 본문처럼 텍스트가 중심인 한국어 인쇄 문서에 추천합니다. 단일 본문 영역을 여러 페이지 처리할 때 기본 선택입니다.",
        "format": "TXT를 추천합니다. 문단 복원과 선택적 Kiwi 띄어쓰기 보정·고유명사 사전을 함께 사용할 수 있습니다.",
        "support": "현재 앱: TXT 추출, 페이지·영역 선택, 줄 좌표와 모델 신뢰도 보존, 문단 복원과 사전 보정. Markdown 출력은 아직 지원하지 않습니다.",
        "resources": "CPU와 NVIDIA GPU를 선택할 수 있습니다. 현재 텍스트 샘플에서는 다른 두 모델보다 빠른 처리를 확인했습니다. 속도는 문서와 컴퓨터에 따라 달라집니다.",
        "limits": "표·차트·다단 문서의 구조를 TXT에 보존하지 않습니다. 고유명사·띄어쓰기·글자 오류는 원문과 비교하세요. 모델 신뢰도는 실제 정확도 점수가 아닙니다.",
    },
    "vl16": {
        "name": "PaddleOCR-VL 1.6",
        "documents": "표·차트·수식·그림·다단 배치가 있는 보고서나 논문처럼 복잡한 문서에 추천하는 모델입니다.",
        "format": "복잡한 문서는 Markdown을 추천합니다. 전용 환경에서 문서 구조와 이미지를 추출합니다. 본문만 필요하면 기존 TXT 경로를 선택할 수 있습니다.",
        "support": "현재 앱: TXT는 기존 텍스트 인식, Markdown은 공식 v1.6 배치 분석·인식 파이프라인을 사용합니다. Markdown의 블록 위치와 원시 결과를 보존합니다. Kiwi·사용자 사전 보정은 적용하지 않습니다.",
        "resources": "NVIDIA GPU를 우선 권장합니다. CPU도 선택할 수 있지만 특히 느리고 메모리 사용이 클 수 있습니다. GPU에서도 모델에 맞는 실행 환경과 충분한 메모리가 필요합니다.",
        "limits": "구조 분석의 CPU·GPU 초기화는 확인했지만 실제 문서의 품질 검증은 남아 있습니다. 표 셀·숫자·수식·읽기 순서와 생성·누락 오류를 원문에서 확인하세요. 차트는 이미지로 보존합니다.",
    },
    "qwen": {
        "name": "Qwen3-VL 2B",
        "documents": "이미지·텍스트가 섞인 페이지를 읽거나 기본 OCR에서 오류가 많은 일부 페이지를 다른 모델과 비교할 때 사용할 후보입니다.",
        "format": "현재는 TXT를 추천합니다. 구조화 Markdown 지원 여부와 품질은 별도로 평가할 예정입니다.",
        "support": "현재 앱: Qwen3-VL-2B-Instruct를 로컬에서 실행해 보이는 글자를 옮깁니다. 줄 좌표·신뢰도와 별도 Kiwi·사용자 사전 보정, 구조화 Markdown은 제공하지 않습니다.",
        "resources": "NVIDIA GPU를 우선 권장합니다. CPU에서는 긴 처리 시간과 많은 메모리가 필요할 수 있습니다. 모델과 문서에 따라 GPU 메모리 사용도 달라집니다.",
        "limits": "원문에 없는 생성·누락과 읽기 순서 오류가 생길 수 있습니다. 숫자·고유명사 등은 원문과 비교하세요. 다른 모델보다 항상 정확하다고 보장하지 않습니다.",
    },
}


class ModelInfoDialog(QDialog):
    """선택 모델과 장치의 안내를 표시하며 모델 실행이나 설정 변경은 하지 않는다."""

    def __init__(self, engine: str, device: str, parent=None):
        """안내 내용을 선택 시점의 모델·장치로 고정해 스크롤 가능한 창을 만든다.

        Raises:
            ValueError: 등록하지 않은 모델이나 장치를 요청한 경우.
        """
        if engine not in MODEL_GUIDES or device not in ("cpu", "gpu"):
            raise ValueError("설명을 표시할 모델과 처리 장치를 확인하세요.")
        super().__init__(parent)
        guide = MODEL_GUIDES[engine]
        self.setWindowTitle(f"모델 설명 · {guide['name']}")
        self.resize(640, 570)
        layout = QVBoxLayout(self)
        title = QLabel(guide["name"])
        title.setStyleSheet("font-size:18px;font-weight:700;")
        layout.addWidget(title)
        chosen = QLabel(f"선택 장치: {'CPU' if device == 'cpu' else 'GPU · NVIDIA'}")
        layout.addWidget(chosen)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        sections = QVBoxLayout(content)
        for heading, key in (
            ("권장 문서", "documents"),
            ("권장 출력 형식", "format"),
            ("현재 앱 지원", "support"),
            ("속도와 자원", "resources"),
            ("확인할 부분", "limits"),
        ):
            label = QLabel(heading)
            label.setStyleSheet("font-weight:700;")
            sections.addWidget(label)
            explanation = QLabel(guide[key])
            explanation.setWordWrap(True)
            explanation.setTextFormat(Qt.TextFormat.PlainText)
            explanation.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            sections.addWidget(explanation)
        sections.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        close = QPushButton("닫기")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        layout.addWidget(close)
