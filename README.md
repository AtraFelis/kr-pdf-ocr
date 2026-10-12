# 한국어 PDF OCR 및 TXT 변환

Windows에서 로컬 AI 모델로 한국어 PDF를 인식하고, 페이지·영역 선택과 문단 복원을 거쳐 TXT로 저장하는 프로젝트입니다. 프로그램 이름은 아직 확정하지 않았습니다.

## 문서

- [기획서](docs/PLAN.md)
- [개발 목록](docs/TASKS.md)
- [문서 분류와 저장 위치](docs/README.md)
- [Git 컨벤션](docs/rules/GIT_CONVENTIONS.md)
- [GitHub 저장소 설명](docs/GITHUB_DESCRIPTION.md)
- [문단 복원](docs/TEXT_RESTORATION.md)
- [고유명사 사용자 사전 설계·개발 예정](docs/USER_DICTIONARY.md)
- [OCR 모델 선택 기록](docs/history/MODEL_SELECTION.md)
- [OCR 실행 기록](docs/history/OCR_SETUP.md)
- [기능 구현·검증 기록](docs/history/IMPLEMENTATION_LOG.md)
- [페이지·영역 선택](docs/PAGE_SELECTION.md)
- [데스크톱 사용법](docs/DESKTOP_APP.md)

## 폴더

- `src/`: 프로그램 소스
- `docs/`: 기획·개발 목록·기능 사용법
- `docs/rules/`: 코딩·Git·개발 절차 규칙
- `docs/history/`: 개발 결정·실행·검증 기록
- `models/`: 로컬 OCR 모델
- `samples/input/`: 실제 PDF 샘플
- `samples/expected/`: 샘플에 대응하는 정답 TXT
- `output/`: 실행 결과

## 현재 상태

Python 3.12 프로젝트 가상환경과 PaddleOCR CPU 시험 코드가 준비되어 있습니다. 샘플 1~2페이지를 300 DPI로 인식해 페이지별 TXT, 좌표·신뢰도 JSON, 페이지 이미지와 실행 요약을 저장했습니다.

PaddleOCR CPU와 PaddleOCR-VL·Qwen GPU 후보를 비교했습니다. 최종 모델은 아직 확정하지 않았습니다. 한국어·영어를 우선하고 명확한 한자 병기는 기본적으로 제외하며 원시 결과를 별도로 보존합니다. 단일 본문 문단 복원·선택적 로컬 띄어쓰기 보정·데스크톱 화면이 구현되어 있으며 페이지 간 연결·배포본은 후속 작업입니다.

다음 개발은 고유명사 사용자 사전입니다. 단어 사전을 만들어 Kiwi 띄어쓰기 보정에 반영하고, 저장 OCR 결과로 적용 전후를 비교하는 기능을 계획했습니다. 현재는 문서에 반영한 기획 단계이며 사전 관리 화면·실행 옵션은 아직 없습니다.

## 실행 방법

**화면으로 사용하려면 프로젝트 폴더의 `start.bat`를 더블 클릭하세요.** PDF 미리보기·마우스 영역 선택·OCR 실행·결과 편집·TXT 저장을 지원합니다.

모델 아래에서 CPU 또는 NVIDIA GPU를 선택합니다. CPU 선택 시 처리 속도와 CPU 사용량 안내가 표시됩니다. GPU를 선택했는데 실행할 수 없으면 오류를 안내하므로 환경을 확인하거나 CPU로 바꿔 주세요. 설치 환경별 명령은 AGENTS.md를 참조하세요.

명령행에서도 페이지 선택·제외와 영역 지정을 지원합니다. `--pages`를 생략하면 전체 페이지를 처리합니다. 선택한 페이지의 결과는 `combined.txt`에도 합쳐 저장합니다.

프로젝트 루트에서 PowerShell로 실행합니다. 최초 모델 다운로드 후 OCR에서는 Python 소켓 연결을 차단하고 로컬 모델 파일만 사용합니다. 운영체제 방화벽에 의한 차단 시험은 아직 수행하지 않았습니다.

```powershell
.\.venv\Scripts\python.exe -m pdf_ocr.cli samples/input/sample.pdf --pages 1-2 --repair-spacing --output "output/ocr-$(Get-Date -Format yyyyMMdd-HHmmss)"
```

출력 경로는 존재하지 않는 새 폴더를 지정합니다. `page-001-raw.txt`는 원시 인식 결과, `page-001.txt`는 병기 한자 제외 및 문단 복원 결과입니다. `--repair-spacing`은 선택적 띄어쓰기 보정이고, `--keep-line-breaks`로 기본 문단 복원을 끌 수 있습니다. `--keep-hanja`로 병기를 유지할 수 있습니다. 독립 한자 및 한글로 오인식된 한자까지 자동 삭제하지는 않습니다.

`--engine qwen`으로 Qwen GPU 후보를, `--engine vl`로 PaddleOCR-VL 1.5를, `--engine vl16`으로 1.6을 시험할 수 있습니다. `--vl-lines`는 VLM을 기존 검출 영역별로 실행하는 비교 옵션입니다. 기본 PaddleOCR의 좌표는 문단 복원에 사용합니다. 좌표 없는 VLM 결과는 모델이 생성한 문단 형태를 보존합니다. 모호한 연결과 보정 제안은 페이지 JSON의 `restoration.reviews`에서 확인하며 모든 결과는 원문 대조가 필요합니다.

설치·검사 명령은 [AGENTS.md](AGENTS.md), 모델 정보와 시험 한계는 [OCR 실행 기록](docs/history/OCR_SETUP.md)을 참조하세요.
