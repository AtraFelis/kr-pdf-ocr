# 한국어 PDF OCR 및 TXT·Markdown 추출

Windows에서 로컬 AI 모델로 한국어 PDF를 인식하고, 페이지·영역 선택과 문단 복원을 거쳐 TXT로 저장하는 프로젝트입니다. VL 1.6 구조 분석과 Markdown 출력의 첫 연결도 제공하며 제공된 샘플의 GPU 처리·저장·취소와 CPU 부분 영역을 확인했습니다. 인식 정확도는 추가 개선이 필요합니다. 프로그램 이름은 아직 확정하지 않았습니다.

## 문서

- [기획서](docs/PLAN.md)
- [개발 목록](docs/TASKS.md)
- [문서 분류와 저장 위치](docs/README.md)
- [Git 컨벤션](docs/rules/GIT_CONVENTIONS.md)
- [코딩 컨벤션·Docstring](docs/rules/CODING_CONVENTIONS.md)
- [GitHub 저장소 설명](docs/GITHUB_DESCRIPTION.md)
- [문단 복원](docs/TEXT_RESTORATION.md)
- [고유명사 사용자 사전 사용법](docs/USER_DICTIONARY.md)
- [Markdown 사용법·전용 환경](docs/MARKDOWN_EXPORT.md)
- [모델 안내·Markdown 출력 설계](docs/MODEL_AND_EXPORT.md)
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
- `output/`: 실행 결과. 이전 실행 결과는 `output/_archive/`에 보관(세부 위치는 [문서 최신화 기록](docs/history/DOCS_STATUS_REFRESH.md) 참조)
- `user_data/dictionaries/`: 로컬 사용자 사전(Git 제외)

## 현재 상태

2026-10-13 기준 PR #8이 병합되어 데스크톱 화면과 로컬 OCR·TXT/Markdown 저장 기능을 사용할 수 있습니다. Python 3.12의 화면/VLM 환경, PP-OCRv5 CPU·GPU 전용 환경과 VL 1.6 구조 분석 전용 환경을 분리합니다. 샘플의 실행·저장·취소는 확인했으며 일반 문서 인식 품질과 배포는 추가 검증이 필요합니다.

PaddleOCR CPU와 PaddleOCR-VL·Qwen GPU 후보를 비교했습니다. 최종 모델은 아직 확정하지 않았습니다. 한국어·영어를 우선하고 명확한 한자 병기는 기본적으로 제외하며 원시 결과를 별도로 보존합니다. 단일 본문 문단 복원·선택적 로컬 띄어쓰기 보정·데스크톱 화면이 구현되어 있으며 페이지 간 연결·배포본은 후속 작업입니다.

고유명사 사용자 사전을 만들고 Kiwi 띄어쓰기 보정에 적용할 수 있습니다. 사전 관리에서 단어 편집·TXT 가져오기/내보내기를 제공하며, 저장 OCR 결과로 사전 적용 전후를 별도 창에서 비교합니다. 재보정은 현재 편집 내용을 보존합니다. PR 리뷰 수정과 샘플의 보정 중단을 검증·수정했고 [짧은 대사·문장부호 재인식 후보](docs/SHORT_TEXT_RETRY.md)도 제공합니다. `gec_kr`의 CPU/GPU 합성 20개 평가를 완료했지만, 핵심 오자·문장부호 미해결과 정상 문장 변경으로 앱 도입은 보류했습니다. [평가 사용법·제한](docs/GEC_EVALUATION.md)을 참고하세요. KoGEC 두 모델도 공개 토큰 설정의 불일치를 확인해 정식 평가·도입을 보류했습니다. [KoGEC 확인 기록](docs/history/KOGEC_CHECKPOINT.md)을 참고하세요. 현재 OCR·Kiwi·사용자 사전·VLM 재인식 흐름을 유지합니다. 순서는 [개발 목록](docs/TASKS.md)을 따릅니다.

텍스트 중심 문서는 PP-OCRv5 + TXT를 기본 흐름으로 삼습니다. 표·차트·수식·다단 문서의 VL 1.6 공식 파이프라인과 Markdown·이미지 저장을 연결했습니다. [전용 환경·사용법과 검증 범위](docs/MARKDOWN_EXPORT.md)를 확인하세요. 모델 선택 옆의 ⓘ 아이콘을 클릭하면 권장 문서·출력 형식·현재 지원 범위를 확인할 수 있습니다.

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
