# 고유명사 사용자 사전

상태: **첫 구현 완료**. PP-OCRv5의 Kiwi 보정과 좌표가 있는 저장 OCR의 재보정을 지원한다. 요구사항은 [기획서](PLAN.md#38-고유명사-사용자-사전), 작업 순서는 [개발 목록](TASKS.md), 검증 범위는 [구현 기록](history/USER_DICTIONARY_IMPLEMENTATION.md)을 참조한다.

## 화면에서 사용

1. **사전 관리 → 새 사전**에서 이름을 지정하고 한 줄에 한 단어를 입력한다. 단어 수정·삭제는 해당 줄을 편집한다.
2. **TXT 가져오기**로 UTF-8/BOM 단어 목록을 현재 목록에 병합한다. 실패하면 기존 입력을 유지한다.
3. **사전 저장** 후 왼쪽 선택 상자에서 사용할 사전을 선택한다. 한 작업에 하나를 사용하며 **사용하지 않음**으로 끌 수 있다.
4. PP-OCRv5와 **한국어 띄어쓰기 보정 제안**을 선택한 뒤 OCR을 실행한다. VL·Qwen에서는 사전 선택을 비활성화하며 이유를 안내한다.
5. 오류가 잦은 이름을 추가한 뒤 **현재 OCR 재보정·비교**를 누른다. OCR을 다시 하지 않고 현재 작업의 원시 페이지 JSON 전체를 재보정한다.
6. 다른 작업의 단일 페이지는 **저장 OCR 열어 비교**에서 `page-*.json`을 선택한다. 여러 저장 페이지를 한 번에 처리하려면 아래 CLI에 작업 결과 폴더를 지정한다.
7. 비교 창에서 **공백 보정 전 / 사전 없이 Kiwi 보정 / 선택 사전으로 Kiwi 보정**을 대조하고 **재보정 결과 TXT 저장**을 누른다.

재보정은 원시 OCR에서 출발하며 오른쪽의 사용자 편집본을 입력으로 쓰거나 덮어쓰지 않는다. 편집본에 필요한 수정을 옮길 때는 직접 확인한다. 비교 결과는 읽기 전용이며 별도 UTF-8 TXT로 저장한다. 취소·실패하면 완료된 페이지의 비교 결과와 현재 편집본을 보존하고 성공으로 표시하지 않는다.

## 입력과 저장

- 사전 이름은 1~100자, 단어는 최대 10,000개·항목당 100자다. 제어 문자와 잘못된 형식을 거부한다.
- 빈 줄·중복은 정리한다. 앞뒤 공백과 연속 공백을 정리하되 단어 내부 공백·글자·대소문자를 보존한다.
- `푸른별 연구소`와 `푸른별연구소`처럼 공백 외 글자가 같고 표기가 다른 항목은 충돌 오류로 알려준다. 하나만 남긴 뒤 다시 저장한다.
- 잘못된 JSON·버전·인코딩·빈 사전은 거부한다. 기존 사전 덮어쓰기·파일 삭제·미저장 편집 폐기는 확인한다.
- **TXT 내보내기**는 한 줄당 한 단어의 UTF-8 파일을 저장한다.

사전은 `user_data/dictionaries/`의 JSON으로 저장한다. 파일명은 생성 ID이며 화면에는 사전 이름과 단어 수를 표시한다. `user_data/` 전체는 Git에서 제외한다. 형식 예시는 실제 문서에서 가져오지 않은 합성 이름이다.

```json
{"version": 1, "name": "예시 작품", "words": ["하루카", "푸른별 연구소"]}
```

작업 시작 시 사전을 별도 JSON으로 고정한다. 이후 원래 사전을 수정해도 실행 조건은 바뀌지 않는다. 출력의 `dictionary.json`은 당시 사전이며 이름·버전·단어 수·SHA-256 식별값을 페이지 결과와 OCR 요약에 기록한다. 작업 파일·사전·OCR 결과는 로컬에만 저장하며 외부 전송·Git 추적을 하지 않는다.

## 보정 원칙과 제한

문단 복원 후 Kiwi `add_user_word(word, tag="NNP", score=0.0)`로 단어를 등록하고 문단별 `space(reset_whitespace=True)`를 실행한다. 별도의 기본 Kiwi로 같은 입력을 보정해 사전 미적용 비교 결과도 만든다. 사전을 사용하면 두 보정 모델을 준비하므로 메모리와 시간이 늘어날 수 있다.

공백 외 글자가 하나라도 달라지면 적용을 중단한다. OCR이 잘못 읽은 이름을 사전 단어로 자동 치환하지 않는다. 문단 경계도 연결하지 않는다. 등록한 이름이 항상 선택된다고 보장하지 않으며 강제로 표기를 치환하지 않는다.

문장에 등록 이름과 같은 글자열이 있으면 `dictionary_context_review`에 등록 단어와 적용 전후를 기록한다. 일반 단어와 겹치거나 짧은 이름이 긴 이름에 포함된 경우도 검토 대상으로 남긴다. 이는 실제 오류 확정이나 정확도 점수가 아니다. 변경 문단은 기존 `spacing_suggestion`에도 기록한다.

좌표가 없거나 같은 높이에 영역이 겹치는 결과는 Kiwi를 적용하지 않는다. 저장 결과에 사전을 명시한 재보정에서는 이런 페이지를 오류로 알린다. VL·Qwen의 인식 단계·자체 문단 출력에 사전을 적용하는 기능은 아직 지원하지 않는다. 전체 문서에서의 품질 개선은 원문과 같은 정답으로 추가 평가해야 한다.

## 명령행

프로젝트 루트의 PowerShell에서 실행한다. 사전 파일은 화면에서 저장한 실제 JSON 경로로 바꾸고 출력은 존재하지 않는 새 폴더를 지정한다.

```powershell
# PP-OCRv5: 사전은 --repair-spacing과 함께 사용
.\.venv-paddle\Scripts\python.exe -m pdf_ocr.cli samples/input/sample.pdf --pages 1 --device cpu --repair-spacing --dictionary user_data/dictionaries/실제파일.json --output "output/dictionary-$(Get-Date -Format yyyyMMdd-HHmmss)"
# 저장 단일 페이지 또는 결과 폴더: OCR 모델 재실행 없음
.\.venv\Scripts\python.exe -m pdf_ocr.restore output/_archive/cleanup-20261013-150057/ocr-run-02 --repair-spacing --dictionary user_data/dictionaries/실제파일.json --output "output/reprocess-$(Get-Date -Format yyyyMMdd-HHmmss)"
```

재보정은 `combined.txt`(최종), `without-dictionary.txt`(사전 미적용), `before-spacing.txt`(공백 보정 전), 페이지 JSON·TXT와 사전 스냅샷을 저장한다. 단일 페이지에서는 기존 `restored.txt`와 `restoration.json`도 유지한다. 비교 기준과 제안은 `restoration.spacing`·`restoration.reviews`에 있다.

## 저장 결과 경로

2026-10-13 정리 이전의 예제 입력은 `output/_archive/cleanup-20261013-150057/`로 이동했다. 새로 실행한 결과를 사용할 때는 명령의 입력을 실제 페이지 JSON 또는 결과 폴더로 바꾼다. 보관 폴더 이름은 이번 컴퓨터의 정리 기록이며 다른 환경에 자동 생성되지 않는다.
