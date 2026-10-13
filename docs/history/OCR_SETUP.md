# OCR 실행 환경 및 샘플 시험

> 상태 안내(2026-10-13): 본문은 당시 실행·개발 기록이다. PR #8은 병합됐으며 현재 구현·다음 작업은 [개발 목록](../TASKS.md)을 따른다. 이전 output 경로와 검증 수치의 해석은 [문서 최신화 기록](DOCS_STATUS_REFRESH.md)을 참조한다.

## 실행 환경

- Windows, AMD Ryzen 7 9700X, NVIDIA RTX 5070. 초기 PaddleOCR 시험은 CPU 8스레드만 사용했다. 이후 GPU 비교 결과는 아래 추가 비교 절에 기록한다.
- Python 3.12.14 프로젝트 `.venv`. PaddlePaddle 3.2.0, PaddleOCR 3.3.0, PaddleX 3.3.13. 전체 의존성 버전은 `requirements.lock.txt`에 기록한다.
- PDF 렌더링은 pypdfium2, 구조 확인은 pypdf, 검사 도구는 Ruff와 pytest를 사용한다.
- 프로그램 코드의 역할은 PDF 렌더링, 로컬 OCR 엔진, 시험 CLI로 분리한다. 초기 시험은 명령행으로 진행했으며 현재 데스크톱 화면은 PySide6를 사용한다. [사용법](../DESKTOP_APP.md)을 참조한다.

## 모델 정보

- 문자 영역 검출: `PP-OCRv5_mobile_det`.
- 문자 인식: `korean_PP-OCRv5_mobile_rec`. 공식 지원 언어는 한국어·영어이며 한자 인식은 보장하지 않는다.
- 공식 추론 모델은 `models/`에 저장한다. 원본 다운로드 주소와 받은 아카이브의 SHA-256은 `models/manifest.json`에 기록한다. 이 해시는 받은 파일 식별용이며 공식 서명 검증을 뜻하지 않는다.
- PaddleOCR 프로젝트는 Apache-2.0 라이선스를 사용한다. 배포 전 모델 배포물의 별도 조건과 고지 사항을 다시 확인한다.
- 공식 자료: https://github.com/PaddlePaddle/PaddleOCR 및 https://www.paddleocr.ai/latest/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html

## 수행한 시험

입력: 로컬 `samples/input/sample.pdf`의 PDF 페이지 1~2. 전체 문서는 11페이지이고 기존 텍스트 레이어가 있다. OCR은 텍스트 레이어를 읽지 않고 페이지를 300 DPI 이미지로 렌더링해 실행했다.

실행 결과: `output/ocr-run-02/`. 1페이지 21개 텍스트 영역, 2페이지 24개 텍스트 영역을 인식하고 UTF-8 TXT와 위치·신뢰도 JSON을 저장했다. 검출 영역 단위 위치이며 문자별 위치는 아니다. 문단 읽기 순서 보정은 아직 구현하지 않았다.

모델 초기화 약 2.10초, 페이지 OCR 약 7.10초와 7.47초. 페이지별 기록 시점의 프로세스 RSS는 약 421MiB와 425MiB다. 렌더링·전체 저장 시간을 포함한 총 시간이나 최대 메모리 측정값은 아니다.

모델 로딩 및 OCR 전에 Python 소켓의 연결 함수를 차단한 실행이 성공했다. 로컬 모델 경로를 명시하고 모델 호스트 연결 확인도 비활성화했다. 운영체제 차원의 전체 네트워크 차단 및 네이티브 라이브러리의 모든 통신 여부까지 검증한 것은 아니다.

## 결과와 한계

- 첫 페이지의 작은 한자 병기가 결과에서 누락됐다.
- 여러 본문 줄에서 단어 사이 공백이 누락되고 일부 문자·문장부호 오류가 보인다.
- TXT는 원시 OCR 줄바꿈을 유지한다. 문단 복원 품질을 평가한 결과가 아니다.
- 초기 시험 당시에는 정답 TXT가 없어 문자 오류율을 계산하지 않았다. 이후 첫 페이지 정답 초안으로 수행한 비교는 아래에 기록한다. 기존 텍스트 레이어는 원문 대조 없이 정답으로 취급하지 않는다.
- 영어·혼합 언어 전체, 나머지 9페이지, 사용자 영역 선택과 패키징은 미검증이다. 이후 추가한 GPU 후보 실행은 아래에 기록한다.
- 첫 실행 `output/ocr-run-01/`은 Paddle 사용자 캐시 초기화 권한 문제로 실패한 빈 폴더다. 실제 결과는 `ocr-run-02`를 사용한다.

## 추가 비교 및 요구사항 변경

사용자 최신 지시에 따라 한자 인식 자체는 필수 목표에서 제외했다. 한국어 바로 뒤 한자와 한국어 뒤 한자만 든 괄호를 병기로 판단해 TXT에서 제외한다. 원시 결과와 JSON은 보존하며, 독립 한자나 한글로 오인식된 부분은 추측으로 삭제하지 않는다. 원문과 전혀 다른 한글로 인식된 병기는 필터로 해결할 수 없는 한계다.

PyTorch 2.9.1+cu128, torchvision 0.24.1+cu128, Transformers 5.19.0을 추가했다. RTX 5070(12,227MiB)의 CUDA 연산을 확인했고 추가 OCR을 GPU에서 실행했다. 기존 PaddlePaddle은 CPU 버전을 유지한다. 재설치 시 requirements.lock.txt와 PyTorch CUDA 12.8 패키지 인덱스를 함께 사용한다.

후보는 공식 `PaddlePaddle/PaddleOCR-VL-1.5` 및 `Qwen/Qwen3-VL-2B-Instruct`다. 두 모델 카드의 라이선스는 Apache-2.0이며 배포 고지는 별도 검토한다. 출처와 고정 다운로드 리비전은 각 models 하위 download-manifest.json에 기록한다. Transformers 내장 구현으로 로컬 파일만 읽고 원격 코드 실행은 허용하지 않았다.

PaddleOCR-VL의 페이지 직접 인식은 2페이지에서 본문을 출력했지만 1페이지에서는 단어 반복으로 2,048토큰 상한에 도달했다(`output/vl-run-03`). 공식 직접 실행 예제는 요소 단위 인식용이므로 이번 전체 페이지 시험 실패를 모든 배포 방식의 성능으로 일반화하지 않는다. 생성 캐시 기본 비활성화로 느렸던 실행은 중단했고 use_cache=True로 다시 수행했다.

검출 줄 영역별 PaddleOCR-VL(`output/vl-lines-01`)은 1페이지를 약 15.27초에 처리했다. 공백 일부를 개선했지만 한자 부근의 한글 오인식 등은 남았다. 좌표는 기존 검출기에서 가져오며 VLM 인식 신뢰도는 제공되지 않아 null로 기록한다.

Qwen은 `output/qwen-run-01`에 1~2페이지를 처리했다. 1페이지 약 38.85초이며 원시 결과와 병기 제외 결과를 분리했다. 본문을 문단 형태로 출력하지만 원문과 다른 글자도 있으므로 교정된 정답으로 취급하지 않는다. 페이지 직접 인식은 줄별 좌표·신뢰도를 제공하지 않아 null로 기록한다.

첫 페이지 전체(제목·하단 쪽수 포함)의 정답 TXT 초안을 300 DPI 원문 이미지와 대조해 `samples/expected/sample-page-001.txt`에 작성했다. 사용자가 확정한 정답은 아니며 한 페이지에 한정된 비교다. 원본 문서와 마찬가지로 저장소에는 추가하지 않는다.

병기 한자를 같은 규칙으로 제외한 첫 페이지 비교 결과:

- PaddleOCR: 공백 무시 문자 오류율 약 1.92%, 공백 포함 약 15.79%.
- 검출 줄별 PaddleOCR-VL: 공백 무시 약 2.64%, 공백 포함 약 7.62%.
- Qwen 페이지 인식: 공백 무시 약 2.88%, 공백 포함 약 2.72%.

오류율은 삽입·삭제·치환 편집 거리 / 정답 문자 수다. 공백 포함 평가에서는 연속 공백·줄바꿈을 한 칸으로 정규화하므로 문단 경계의 정확도를 측정하지 않는다. 공백 무시 평가는 모든 공백을 제거한다. 두 지표의 분모가 달라 수치의 단순 차이가 공백 오류율을 뜻하지 않는다. 비교 명령은 다음과 같다.

```powershell
.\.venv\Scripts\python.exe scripts/compare_ocr.py samples/expected/sample-page-001.txt output/ocr-run-02/page-001.txt output/vl-lines-01/page-001.txt output/qwen-run-01/page-001.txt --exclude-hanja
```

Qwen은 공백·문단 형태 면에서 유리하고 기존 PaddleOCR은 이 페이지의 글자 자체 오류가 더 적다. 둘 다 최종 모델로 확정하지 않고 결과를 보존한다. 독립 한자, 한자→한글 오인식, 영어 혼합 문서 전체와 CPU VLM 실행은 아직 검증 범위를 넓혀야 한다.

## 다음 단계

추가 VL 1.6 시험은 `output/vl16-run-01`에 보존했다. 모델 리비전은 `c5630abae1d940eafe0697512a0325494b02ab42`이며 같은 로컬 Transformers 환경을 사용했다. 1~2페이지에 토큰 상한 도달은 없었고, 첫 페이지 공백 포함 오류율 약 1.09%, 공백 무시 약 0.96%였다. 세부 해석은 [모델 선택 기준](MODEL_SELECTION.md)을 참조한다. 원시 결과·한자 제외 결과를 보존하며 줄 좌표·신뢰도가 없는 한계는 유지된다.

기존 PaddleOCR 위치 정보를 이용한 단일 본문 문단 복원과 선택적 Kiwi 띄어쓰기 보정이 구현되었다. 사용 방법과 검증 범위는 [문단 복원 문서](../TEXT_RESTORATION.md)와 [기능 구현·검증 기록](IMPLEMENTATION_LOG.md)을 참조한다. Qwen은 품질 비교 후보로 유지하고, 추가 페이지 정답으로 문자 보존 및 공백 복원 품질을 확인한 뒤 기본 모델을 결정한다. 페이지 제외·영역 선택·데스크톱 화면은 이후 구현했으며 현재 후속 작업은 [개발 목록](../TASKS.md)을 참조한다.

## CPU·GPU 장치 선택 추가 (2026-10-12)

PP-OCRv5의 CPU 고정을 해제하고 모델과 장치를 별도로 선택한다. 공식 Windows 설치 안내와 RTX 5070 지원 조건에 따라 PaddlePaddle-GPU 3.2.2 / CUDA 12.9를 도입했다. [공식 Windows 설치 안내](https://www.paddlepaddle.org.cn/documentation/docs/en/install/pip/windows-pip_en.html), [GPU 지원 조건](https://www.paddlepaddle.org.cn/documentation/docs/zh/install/Tables_en.html).

기존 `.venv`에 GPU PaddlePaddle을 추가했을 때 PyTorch와 CUDA DLL을 함께 로딩하며 `WinError 127`이 발생했다. 가져오기 순서를 바꾸어도 다른 DLL에서 실패했다. `.venv`는 기존 CPU PaddlePaddle 3.2.0 / PyTorch CUDA 12.8 구성을 유지하고, `.venv-paddle`에는 GPU PaddlePaddle과 필요한 패키지만 설치했다. PyTorch는 전용 환경에 설치하지 않는다. GUI는 PP-OCRv5 실행에 전용 환경을 사용하며 설치 버전은 `requirements-paddle.lock.txt`에 고정했다.

동일한 샘플 첫 페이지를 300 DPI, 전체 영역, 문단 복원·Kiwi 보정으로 GUI에서 실행한 결과:

- CPU: 요청 `cpu`, 실제 `cpu`, 21개 영역, 처리 구간 약 7.60초, 초기화 약 2.89초, 기록 시점 RSS 약 1,243MiB.
- GPU: 요청 `gpu`, 실제 `gpu:0`, 21개 영역, 처리 구간 약 1.50초, 초기화 약 3.14초, 기록 시점 RSS 약 2,086MiB.

처리 구간은 OCR·문단 복원·보정을 포함하며 모델 초기화·PDF 렌더링·후속 파일 저장은 제외한다. RSS는 최대 메모리나 GPU VRAM이 아니다. 한 페이지의 단일 실행이므로 일반적인 속도 향상 비율이나 정확도 우열을 확정하지 않는다. 최종 결과 사이에는 한 글자의 편집 거리 차이가 있었다. GPU 전환만으로 정확도 향상을 보장하지 않는다.

GUI 실행 기록은 `output/device-desktop-run/`과 각 작업 결과 폴더에 로컬 보관한다. VL 1.6도 명시적 GPU 선택으로 첫 페이지를 완료했으며 처리 구간 약 8.60초였다(`output/device-vl16-gpu-01/`). PyTorch CUDA 연산과 두 환경의 의존성·Ruff 검사를 확인했다. 이번 변경에서는 pytest 테스트 모음을 실행하지 않았으며 VLM의 전체 페이지 CPU 처리와 모든 장치별 실패·취소 조건 확인은 남아 있다.
