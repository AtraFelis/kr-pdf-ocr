# VL 1.6 구조 분석과 Markdown 출력

상태: **사용자 샘플 실행·저장·취소와 회귀 검증 완료**. GPU 전체 2페이지와 CPU 부분 영역을 확인했다. 일반 문서 인식 품질·CPU 전체 문서·다양한 DPI는 추가 평가한다. [샘플 검증 기록](history/MARKDOWN_SAMPLE_VALIDATION.md)을 참조한다.

## 화면에서 사용

1. 모델을 **PaddleOCR-VL 1.6**, 출력 형식을 **Markdown · 문서 구조**로 선택한다. 모델 변경만으로 형식을 바꾸지 않는다. PP-OCRv5·Qwen에서 Markdown을 요청하면 실행 전에 이유를 안내한다.
2. CPU 또는 GPU를 선택하고 기존 방식으로 페이지·제외·영역을 지정한다. 구조 분석은 선택 영역을 잘라 적용한다.
3. OCR 실행 후 **원문 편집**에서 Markdown을 수정하거나 **Markdown 미리보기**에서 본문·기본 표·로컬 이미지를 확인한다. 미리보기는 외부 링크·원격 이미지·결과 폴더 밖 파일을 열지 않는다. 공식 HTML의 그림 크기는 표시용 문서에서 조정해 제목과 겹치지 않게 한다. Markdown 원문·그림 파일에는 이를 반영하지 않는다. 수식의 LaTeX 표기는 보존하지만 미리보기의 수식 조판은 지원하지 않는다.
4. **Markdown 저장**을 누르면 `.md`와 새 이미지 폴더를 함께 저장한다. 이미지 폴더를 같이 이동하거나 공유해야 그림이 표시된다. 기존 `.md` 덮어쓰기는 확인하며 기존 이미지 폴더는 바꾸지 않는다.

결과를 받은 형식과 저장 형식을 고정한다. 다음 작업의 출력 선택을 바꿔도 이미 편집 중인 TXT·Markdown을 자동 변환하지 않는다. TXT용 줄 연결·Kiwi·사용자 사전은 Markdown에 적용하지 않는다. Markdown의 한자·원문 구조는 유지하며 TXT의 병기 한자 필터를 적용하지 않는다.

## 실행 환경

기존 `.venv`(화면·직접 VLM TXT), `.venv-paddle`(PP-OCRv5)을 유지하고 `.venv-doc-parser`(구조 분석)를 분리했다. 같은 프로세스에 GPU Paddle과 GPU PyTorch를 함께 넣지 않는다. 전용 환경에는 PyTorch를 설치하지 않는다.

설치한 버전은 PaddleOCR 3.6.0, PaddleX 3.6.1, PaddlePaddle-GPU 3.2.2 / CUDA 12.9이며 전체 버전은 `requirements-structure.lock.txt`로 고정한다. 앱의 기본 PaddleOCR 3.3.0 잠금 파일은 유지했다. 패키지 선언은 두 환경을 수용하도록 `>=3.3.0,<3.7`로 정의하며 설치할 때 각 환경의 잠금 파일을 사용한다.

모델은 `PP-DocLayoutV3`와 `PaddleOCR-VL-1.6`이다. 공식 모델 카드의 라이선스는 Apache-2.0이며 배포 시 고지와 관련 패키지 라이선스를 별도 확인한다. 다운로드 리비전은 각 모델의 `download-manifest.json`에 남는다. 다운로드는 문서를 읽지 않고, 문서 처리에서는 로컬 경로·오프라인 설정·Python 소켓 차단을 사용한다.

프로젝트 루트에서 실행한다. 이 PC에서는 전용 환경·모델 설치와 CPU/GPU 초기화를 완료했다.

```powershell
# 설치: 네트워크 필요, Python 3.12
.\.venv\Scripts\python.exe -m venv .venv-doc-parser
.\.venv-doc-parser\Scripts\python.exe -m pip install -r requirements-structure.lock.txt --extra-index-url https://www.paddlepaddle.org.cn/packages/stable/cu129/
.\.venv-doc-parser\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv-doc-parser\Scripts\python.exe -m pip check
# 모델 다운로드: 기존 .venv의 Hugging Face 패키지 사용
.\.venv\Scripts\python.exe scripts/download_structure_models.py
# 실행 확인한 샘플의 GPU 첫 페이지: 출력은 새 폴더 지정
.\.venv-doc-parser\Scripts\python.exe -m pdf_ocr.cli samples/input/sample_md.pdf --pages 1 --engine vl16 --format md --device gpu --output "output/structure-$(Get-Date -Format yyyyMMdd-HHmmss)"
```

GPU가 없으면 `--device cpu`를 선택한다. 명시적 GPU 오류를 CPU로 바꾸지 않는다. 모델 누락·전용 환경 누락·잘못된 출력 조합은 오류로 알린다. 기존 TXT는 기존 환경·실행 경로를 사용한다.

## 결과와 제한

- `page-001.md`: 공식 변환기의 Markdown, `combined.md`: 완료된 선택 페이지 순서의 통합 결과.
- `assets/`: 공식 결과의 그림·차트 이미지를 페이지별 고유 이름으로 저장한다. 차트를 추정 숫자·설명으로 바꾸는 인식은 껐다.
- `page-001-native.json`: 이미지 저장 전 보존하는 공식 원시 JSON.
- `page-001.json`: 블록 종류·내용·원시 목록 위치·제공된 읽기 순서, 자른 입력 좌표·전체 페이지 좌표·상대 좌표, 이미지 경로 대응과 공식 원시 JSON.
- `summary.json`: 파이프라인·장치·선택/완료 페이지와 정상 완료/실패 상태. 강제 종료 시 요약은 생성되지 않을 수 있으나 이미 쓴 페이지 파일은 남는다.

기본적으로 머리말·각주 등을 출력에서 제외하지 않는다. 모델의 구조 인식 오류·읽기 순서·표 셀·누락·잘린 영역은 원문 대조가 필요하다. 제공되지 않은 문자 신뢰도는 만들지 않는다. 페이지 간 표 병합·제목 단계 재구성은 아직 제공하지 않는다.

출력 폴더는 새 경로로 생성해 기존 결과를 보호한다. 실제 취소와 합성 뒤 페이지 실패에서 저장 완료한 페이지가 유지되는 것을 확인했다. 저장 중 오류가 발생하면 새로 복사한 이미지 폴더가 남을 수 있으며 기존 문서·이미지는 보존한다. 편집 중 추가한 결과 폴더 내부 `assets/` 링크만 이미지 묶음 저장 대상으로 삼으며 외부 이미지 자동 수집은 제공하지 않는다.

공식 API·권장 실행 경로: [VL 1.6 모델 카드](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6), [문서 파이프라인](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html).
