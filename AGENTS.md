# 프로젝트 공통 규칙

## 1. 프로젝트 개요와 적용 범위

Windows에서 로컬 AI 모델로 한국어 PDF를 OCR하고, 선택한 페이지·영역의 텍스트를 문단 단위로 복원하여 UTF-8 TXT로 저장한다. 한국어·영어를 우선하며 한국어에 병기된 한자는 TXT에서 제외한다. 문서 처리는 로컬에서 수행한다.

이 파일은 프로젝트 전체에 적용한다. 상세 기능은 [기획서](docs/PLAN.md), 작업 순서는 [개발 목록](docs/TASKS.md), 프로젝트 안내는 [README](README.md)를 참조한다. 상세 기획을 이 파일에 중복 작성하지 않는다.

## 2. 문서 우선순위와 충돌 처리

프로젝트 문서 간 규칙이나 지시가 충돌하면 AGENTS.md를 정답이자 판단 기준으로 삼는다. README, 기획서, 개발 목록과 코드 주석은 이에 맞춰 정리한다. 단, 최신 사용자 지시와 시스템·개발자 지침은 AGENTS.md보다 우선한다.

충돌을 발견하면 다음 절차를 따른다.

1. 사용자에게 충돌한 문서·항목, 서로 다른 내용, 적용할 규칙을 알린다.
2. 관련 코드와 설정, 문서 작성 맥락을 확인한다. 변경 이력이 있다면 함께 조사한다.
3. 요구사항 변경 미반영, 오래된 지침, 중복 작성, 구현 오류 등 원인을 검토하고 확인된 사실과 추정을 구분한다. 확인할 수 없는 원인은 미확인으로 보고한다.
4. AGENTS.md 자체에도 잘못되거나 오래된 내용이 있는지 검토한다. 규칙의 우선순위를 실제 구현의 정확성을 보장하는 근거로 사용하지 않는다.
5. 정답이 명확한 문서 불일치는 수정하고 사용자에게 결과를 알린다. AGENTS.md의 규칙 변경이나 요구사항 선택이 필요하면 근거와 수정안을 제시하고 사용자 판단을 받는다.
6. 충돌과 관계없는 작업은 계속한다. 영향을 받는 부분에서 임의로 다른 규칙을 선택하지 않는다.

## 3. 개발 명령과 유지 관리

작업 디렉터리: 프로젝트 루트. Python 3.12와 프로젝트 전용 `.venv`를 사용한다. CPU PaddleOCR 및 GPU PaddleOCR-VL 비교 코드가 있으며 데스크톱 앱 배포 빌드는 아직 미설정이다.

```powershell
# 가상환경 생성: 사용 가능한 Python 3.12 실행 파일로 실행
python -m venv .venv
# 최초 환경 구성(네트워크 필요)
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt --extra-index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
# 공식 모델 다운로드(네트워크 필요, 사용자 문서는 읽지 않음)
.\.venv\Scripts\python.exe scripts/download_models.py
.\.venv\Scripts\python.exe scripts/download_vl_model.py
.\.venv\Scripts\python.exe scripts/download_vl_model.py --model qwen
.\.venv\Scripts\python.exe scripts/download_vl_model.py --model paddle16
# OCR 실행: 출력 폴더는 아직 존재하지 않는 새 경로를 지정
.\.venv\Scripts\python.exe -m pdf_ocr.cli samples/input/sample.pdf --pages 1-2 --output "output/ocr-$(Get-Date -Format yyyyMMdd-HHmmss)"
# GPU VLM: 동일한 방식으로 별도 출력, CUDA 불가 시 CPU로 실행
.\.venv\Scripts\python.exe -m pdf_ocr.cli samples/input/sample.pdf --pages 1-2 --engine vl --output "output/vl-$(Get-Date -Format yyyyMMdd-HHmmss)"
# 한국어 품질 비교 후보 Qwen
.\.venv\Scripts\python.exe -m pdf_ocr.cli samples/input/sample.pdf --pages 1-2 --engine vl16 --keep-line-breaks --output "output/vl16-$(Get-Date -Format yyyyMMdd-HHmmss)"
.\.venv\Scripts\python.exe -m pdf_ocr.cli samples/input/sample.pdf --pages 1-2 --engine qwen --output "output/qwen-$(Get-Date -Format yyyyMMdd-HHmmss)"
# 문단 복원과 선택적 한국어 띄어쓰기 보정
.\.venv\Scripts\python.exe -m pdf_ocr.cli samples/input/sample.pdf --pages 1-2 --repair-spacing --output "output/restored-$(Get-Date -Format yyyyMMdd-HHmmss)"
# 저장된 OCR JSON 재처리(모델 재실행 없음)
.\.venv\Scripts\python.exe -m pdf_ocr.restore output/ocr-run-02/page-001.json --repair-spacing --output "output/reprocessed-$(Get-Date -Format yyyyMMdd-HHmmss)"
# 검증
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check src scripts tests
.\.venv\Scripts\python.exe -m ruff format --check src scripts tests
```

이 컴퓨터의 가상환경은 Codex에 포함된 Python 3.12로 생성했다. 전역 `python`이 없거나 다른 버전이면 Python 3.12 실행 파일의 전체 경로를 사용한다. VLM은 로컬 파일과 Transformers 내장 모델 코드만 사용한다. VLM이 제공하지 않는 줄별 좌표·신뢰도를 생성하지 않는다. 단일 본문 문단 복원과 선택적 Kiwi 띄어쓰기 보정이 구현되어 있다. GUI·페이지 간 연결·배포 빌드는 아직 미구현이다.

- 도구를 도입하는 변경에서 실제 확인한 설치·실행·테스트·정적 검사·포맷 검사·빌드 명령을 이 절에 등록한다. 작업 디렉터리와 실행 전제조건을 명시하고 복사해 실행 가능한 형태로 작성한다.
- 명령·구조·의존성이 바뀌면 AGENTS.md도 같은 변경에서 갱신한다. 오래된 지침과 중복 규칙을 제거한다.
- 임시 규칙에는 제거 조건을 적는다. 장시간 작업 전에 지침과 실제 환경이 일치하는지 확인한다.

## 4. 코딩 컨벤션

- 작업 전에 이 파일, 기획서, 개발 목록과 관련 코드를 읽는다. 한 번에 하나의 기능이나 오류를 해결한다.
- PDF 처리, OCR, 페이지·영역 선택, 문단 복원, 저장, 화면 코드를 분리한다.
- OCR 모델은 공통 인터페이스로 연결한다. 원본 인식 결과와 위치 정보를 보존하고 신뢰도를 임의로 만들지 않는다.
- 이름은 역할이 드러나게 작성한다. 주석은 처리 이유를, 한국어 안내는 사용자가 취할 조치를 설명한다.
- 개발 언어와 도구가 결정되면 표준 포맷터·정적 검사와 의존성 버전 관리를 설정한다. 기존 스타일을 따른다.
- 화면의 페이지 번호는 1부터 시작하고 내부 인덱스와 명시적으로 변환한다. 영역은 상대 좌표로 저장하고 회전·확대·해상도 변환을 일관되게 처리한다.
- OCR은 화면을 멈추지 않도록 실행하며 취소·오류 시 완료 결과를 보존한다. TXT는 UTF-8로 저장한다.
- 모델 버전·라이선스·실행 조건을 기록한다.
- 병기 한자를 기본적으로 제외하고 원시 OCR 결과를 따로 보존한다. 한국어 뒤에 붙은 한자 및 한자만 든 괄호를 병기로 처리한다. 독립 한자나 한글로 오인식된 부분을 추측으로 삭제하지 않는다. `--keep-hanja`로 원시 한자를 유지할 수 있다.
- 기본 문단 복원은 단일 본문 영역만 처리한다. 좌표가 없거나 같은 높이에 영역이 겹치면 줄바꿈을 보존하고 확인 대상으로 남긴다. `--keep-line-breaks`로 복원을 끌 수 있다. `--repair-spacing`은 Kiwi 로컬 모델을 사용하는 선택 기능이며 공백을 제외한 글자가 변경되면 적용을 중단한다. 변경 제안과 모호한 연결은 JSON에 기록한다.
- 커밋과 PR은 하나의 변경 목적을 중심으로 구성하고 변경 이유와 검증 결과를 적는다.
- Git 작업은 [Git 컨벤션](docs/GIT_CONVENTIONS.md)을 따른다. 기본 브랜치는 `main`, 작업 브랜치는 `codex/<작업명>`이며 커밋은 `<type>(<scope>): <한국어 설명>` 형식을 사용한다. 관련 파일만 추가하고 커밋 전 스테이징 내용·제외 대상·검증 결과를 확인한다.

## 5. 금지 사항

- 문서와 OCR 결과를 외부 서버에 전송하지 않는다. 모델 다운로드와 로컬 문서 처리를 구분한다.
- 원본 문서와 사용자 편집 결과를 임의로 변경·삭제하지 않는다. 기존 출력 파일 덮어쓰기는 확인을 받는다.
- 모든 줄바꿈을 공백으로 치환하거나 모든 공백을 제거하지 않는다. 문단 복원 과정에서 내용을 요약·추가하지 않고 모호한 연결은 확인 대상으로 남긴다.
- 예외를 숨기거나 실패를 성공으로 표시하지 않는다.
- 실제 문서, 모델 가중치, 출력물과 비밀 정보를 저장소에 추가하지 않는다. 테스트 자료는 합성 자료나 배포 가능한 자료를 사용한다.
- 전역 환경 변경, 기존 작업 강제 초기화, 관계없는 구조 변경을 하지 않는다.
- 모델 지원 언어와 정확도를 확인 없이 단정하지 않는다.

## 6. 검증 절차와 완료 기준

검증은 변경한 기능에 맞춰 수행한다.

- **페이지·영역:** 선택·제외, 잘못된 범위, 높이 1,000px에서 임의의 범위(예: 200px~800px) 선택, 확대·회전·해상도 변경과 경계 문자.
- **문단 복원:** `제조사\n에 → 제조사에`(여기서 `\n`은 줄바꿈), 단어 사이 공백, 실제 문단, 제목·목록과 페이지 연결 옵션.
- **OCR:** 동일한 한국어·영어 및 한자 병기 샘플과 정답 TXT 비교. 병기 한자는 평가에서 제외하되 한국어 손상·독립 한자 오삭제를 검증한다. 인식 오류와 문단 복원 오류를 구분하고 실행 환경·시간·메모리를 기록.
- **실행·저장:** CPU 실행, 암호·손상 PDF, 진행 상태, 취소, 부분 실패, UTF-8 저장. 배포 전 인터넷 연결 없는 문서 처리 확인.

동작 변경에는 필요한 테스트를, 오류 수정에는 재현 사례를 추가한다. 등록된 명령으로 관련 테스트·정적 검사·포맷 검사와 변경에 필요한 실행·빌드 검증을 수행한다. 관련 검사가 통과하고 문서가 최신 상태일 때 완료로 판단한다. 실행하지 못한 검사는 이유를 보고하고 통과했다고 표현하지 않는다.

문서만 변경한 경우에는 규칙 간 모순, 기획서와의 일치, 문서 참조와 등록된 명령의 유효성을 검토한다. 등록된 명령과 현재 구현 상태가 실제 환경과 일치하는지 확인한다.

완료 보고에는 변경 내용, 검증 결과와 남은 제한을 간결하게 적는다. 실제 확인된 항목만 개발 목록에서 완료 처리한다.
