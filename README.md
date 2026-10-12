# 한국어 PDF OCR 및 TXT 변환

Windows에서 로컬 AI 모델로 한국어 PDF를 인식하고, 페이지·영역 선택과 문단 복원을 거쳐 TXT로 저장하는 프로젝트입니다. 프로그램 이름은 아직 확정하지 않았습니다.

## 문서

- [기획서](docs/PLAN.md)
- [개발 목록](docs/TASKS.md)
- [Git 컨벤션](docs/GIT_CONVENTIONS.md)
- [GitHub 저장소 설명](docs/GITHUB_DESCRIPTION.md)
- [문단 복원](docs/TEXT_RESTORATION.md)
- [OCR 모델 선택 기준](docs/MODEL_SELECTION.md)

## 폴더

- `src/`: 프로그램 소스
- `models/`: 로컬 OCR 모델
- `samples/input/`: 실제 PDF 샘플
- `samples/expected/`: 샘플에 대응하는 정답 TXT
- `output/`: 실행 결과

## 현재 상태

Python 3.12 프로젝트 가상환경과 PaddleOCR CPU 시험 코드가 준비되어 있습니다. 샘플 1~2페이지를 300 DPI로 인식해 페이지별 TXT, 좌표·신뢰도 JSON, 페이지 이미지와 실행 요약을 저장했습니다.

PaddleOCR CPU와 PaddleOCR-VL·Qwen GPU 후보를 비교했습니다. 최종 모델은 아직 확정하지 않았습니다. 한국어·영어를 우선하고 명확한 한자 병기는 기본적으로 제외하며 원시 결과를 별도로 보존합니다. 단일 본문 문단 복원과 선택적 로컬 띄어쓰기 보정이 구현되어 있으며 GUI·페이지 간 연결·배포본은 아직 구현되지 않았습니다.

## 실행 방법

프로젝트 루트에서 PowerShell로 실행합니다. 최초 모델 다운로드 후 OCR에서는 Python 소켓 연결을 차단하고 로컬 모델 파일만 사용합니다. 운영체제 방화벽에 의한 차단 시험은 아직 수행하지 않았습니다.

```powershell
.\.venv\Scripts\python.exe -m pdf_ocr.cli samples/input/sample.pdf --pages 1-2 --repair-spacing --output "output/ocr-$(Get-Date -Format yyyyMMdd-HHmmss)"
```

출력 경로는 존재하지 않는 새 폴더를 지정합니다. `page-001-raw.txt`는 원시 인식 결과, `page-001.txt`는 병기 한자 제외 및 문단 복원 결과입니다. `--repair-spacing`은 선택적 띄어쓰기 보정이고, `--keep-line-breaks`로 기본 문단 복원을 끌 수 있습니다. `--keep-hanja`로 병기를 유지할 수 있습니다. 독립 한자 및 한글로 오인식된 한자까지 자동 삭제하지는 않습니다.

`--engine qwen`으로 Qwen GPU 후보를, `--engine vl`로 PaddleOCR-VL 1.5를, `--engine vl16`으로 1.6을 시험할 수 있습니다. `--vl-lines`는 VLM을 기존 검출 영역별로 실행하는 비교 옵션입니다. 기본 PaddleOCR의 좌표는 문단 복원에 사용합니다. 좌표 없는 VLM 결과는 모델이 생성한 문단 형태를 보존합니다. 모호한 연결과 보정 제안은 페이지 JSON의 `restoration.reviews`에서 확인하며 모든 결과는 원문 대조가 필요합니다.

설치·검사 명령은 [AGENTS.md](AGENTS.md), 모델 정보와 시험 한계는 [OCR 실행 기록](docs/OCR_SETUP.md)을 참조하세요.
