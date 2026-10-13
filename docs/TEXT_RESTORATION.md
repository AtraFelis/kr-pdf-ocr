# 문단 복원과 로컬 띄어쓰기 보정

## 현재 동작

OCR 원본 줄과 좌표를 보존하고, 단일 본문 영역의 줄을 위에서 아래로 정렬한다. 대표 줄 높이·줄 간격·들여쓰기·짧은 마지막 줄·글자 크기 변화와 목록 표식을 이용해 문단을 구분한다. 문장 마침표만으로 문단을 끊지 않는다. 문단 사이에는 빈 줄을 넣는다.

한국어 뒤에 조사만 이어지는 등 명확한 규칙에 해당하면 공백 없이 연결한다. 그 밖의 한국어·영어 단어 경계는 공백으로 연결하고 `ambiguous_word_boundary`로 표시한다. OCR이 잃어버린 문자나 문장부호는 생성하지 않는다.

Kiwi 보정 뒤에는 짝이 맞는 한글 인용문의 여는 부호 앞 공백도 확인한다. 앞 글자와 인용 시작이 한글일 때 `문장 중에'인용'이라는 → 문장 중에 '인용'이라는`처럼 공백만 추가한다. 닫는 부호 뒤 조사·원래 부호는 유지하며 짝 없는 부호·영문 아포스트로피에는 적용하지 않는다. ASCII·곡선 따옴표 혼용과 겹낫표·홑낫표를 다룬다. 사전 적용/미적용 결과에 같은 규칙을 사용하고 `spacing.korean_quote_boundaries`에 적용 정책을 기록한다. [인용문 경계 수정 기록](history/QUOTE_SPACING.md)을 참조한다.

OCR이 같은 줄의 닫는 따옴표·마침표 등을 별도 작은 영역으로 인식하면, 본문 오른쪽 끝과 높이가 가까운 유일한 줄에만 연결한다. 연결은 `attached_closing_punctuation`과 모든 원본 줄 인덱스로 기록한다. 부호를 새로 만들거나 원시 텍스트·좌표·신뢰도를 바꾸지 않는다. 크거나 멀거나 후보가 여럿인 부호, 여는 부호와 일반 문자는 추측으로 연결하지 않는다. 작은 부호 때문에 페이지를 다단 문서로 오인해 Kiwi를 건너뛰는 사례를 줄이기 위한 처리다. [오류 샘플 검증](history/OCR_ERROR_SAMPLE.md)을 참조한다.

좌표가 없으면 텍스트의 기존 문단 형태를 보존하고 `missing_geometry`로 표시한다. 같은 높이에 여러 영역이 겹치면 겹침 관련 영역이 4개 이하·전체 유효 영역의 25% 이하일 때 해당 블록의 줄을 보존하고 정상 구간만 부분 복원한다. 모호한 문단은 Kiwi·사전 보정도 제외한다. 겹침이 많으면 기존 순서를 보존해 `overlapping_rows_or_columns`로 표시한다. 부분 복원은 `partial_geometry_applied`와 문단별 `geometry_applied`, `overlapping_region_preserved`에 기록한다. [재발 수정 기록](history/PR12_REVIEW_AND_PAGE17.md)을 따른다. 다단 편집·표·회전 문서·복잡한 각주는 지원 품질을 보장하지 않는다.

## 선택적 띄어쓰기 보정

`--repair-spacing`은 Kiwi 0.24.0과 kiwipiepy_model 0.24.0을 로컬에서 사용한다. 모델은 설치 패키지에 포함되며 실행 중 다운로드하지 않는다. 각 문단에 `Kiwi.space(reset_whitespace=True)`를 적용한다.

공백을 제거한 보정 전후 문자열이 완전히 같아야 적용한다. 글자가 달라지면 오류로 중단한다. 변경된 문단은 `spacing_suggestion`에 전후 텍스트를 기록한다. 기존 모호한 연결 표시도 유지한다. 따라서 이 결과는 확인 가능한 제안이며 고유명사·문학적 표현의 정확성을 보장하지 않는다.

패키지 배포 라이선스와 고지는 앱 패키징 시 검토한다. API 출처: https://bab2min.github.io/kiwipiepy/

## 고유명사 사용자 사전

`--dictionary`로 선택한 JSON의 단어를 Kiwi에 고유명사로 등록한다. 공백 포함 이름을 지원하며 기본 Kiwi의 사전 미적용 결과도 함께 기록한다. 공백 외 글자 보존 조건은 동일하며 OCR 문자 오류를 자동 치환하지 않는다.

첫 적용은 PP-OCRv5와 좌표가 있는 저장 OCR에 한정한다. 사전 선택·관리·재보정 비교 사용법과 기록 형식은 [사용자 사전](USER_DICTIONARY.md)을 참조한다. VL·Qwen은 자동 적용하지 않는다.

## 실행

프로젝트 루트의 PowerShell에서 새 출력 폴더를 지정한다.

```powershell
# OCR부터 문단 복원과 띄어쓰기 보정까지
.\.venv\Scripts\python.exe -m pdf_ocr.cli samples/input/sample.pdf --pages 1-2 --repair-spacing --output "output/paragraphs-$(Get-Date -Format yyyyMMdd-HHmmss)"
# 저장한 JSON만 재처리
.\.venv\Scripts\python.exe -m pdf_ocr.restore output/_archive/cleanup-20261013-150057/ocr-run-02/page-001.json --repair-spacing --output "output/reprocess-$(Get-Date -Format yyyyMMdd-HHmmss)"
```

재처리 도구는 PDF나 OCR 모델을 다시 열지 않는다. 기본 OCR 명령은 문단 복원만 적용하고 Kiwi 보정은 명시적으로 선택한다. `--keep-line-breaks`와 `--repair-spacing`은 함께 사용할 수 없다.

원시 TXT·줄 JSON은 그대로 남기고 최종 TXT에는 문단 결과를 저장한다. 페이지 JSON의 `restoration`은 최종 텍스트, 문단별 원시 줄 인덱스, 확인 항목과 좌표 처리 여부를 담는다. `summary.json`에는 요청한 복원·보정 옵션을 기록한다. 좌표 없는 페이지는 복원 옵션이 켜져 있어도 `geometry_applied=false`이며 별도 문단 재구성을 수행하지 않는다.

## 제한과 검증 기록

17페이지 전체 영역에서 대사 한 줄이 원시 OCR 결과부터 누락되는 검출 문제를 확인했다. 문단 복원·Kiwi가 제거한 사례가 아니며, 드문 겹침의 보정 중단과 별개다. PP-OCRv5 검출 영역 점수 기준을 0.5로 명시한 뒤 동일 이미지의 CPU·GPU 실행에서 원시 결과·최종 TXT 모두 대사를 포함했다. 인식 신뢰도 필터를 해제하거나 해상도 제한을 바꾸는 것만으로는 해당 줄이 복구되지 않았다. [검증 기록](history/OCR_DETECTION_OMISSION.md)을 참조한다.

변경 적용은 프로그램을 재시작하고 OCR을 다시 실행해야 한다. 저장 JSON 재보정은 이미 인식된 글자만 처리하므로 누락된 문장을 복원할 수 없다. 검출 기준 완화로 다른 문서에서는 잡음 영역이 증가할 수 있으며, 글자 오류를 수정하거나 모든 누락을 보장하는 기능은 아니다. PP-OCRv5 실행의 `summary.json.ocr_settings.text_det_box_thresh`로 적용값을 확인한다.

샘플 비교 결과와 실행 조건은 [문단 복원 검증 기록](history/IMPLEMENTATION_LOG.md#문단-복원과-띄어쓰기-보정)을 참조한다.

오류 샘플의 작은 닫는 부호로 인한 보정 중단은 수정됐다. 좌표 누락·광범위한 겹침은 페이지 전체를 보존한다. 드문 겹침은 정상 구간의 부분 복원을 제공하고 GUI에 부분 복원 페이지 수를 표시한다. 상세 영역별 확인·편집 화면과 다양한 문서의 부분 복원 품질 확대는 후속 작업이다. [페이지 사이 문단 연결](PAGE_CONNECTION.md)은 PP-OCRv5 TXT의 선택 옵션으로 제공한다. 단어 경계 완전 자동 판정과 표·다단 처리는 후속 작업이다. 재인식 후보 비교·편집기 반영은 [별도 기능](SHORT_TEXT_RETRY.md)으로 제공한다. 현재 문단 경계는 휴리스틱이므로 원문 미리보기와 대조해야 한다.

## 저장 결과 경로

2026-10-13 정리 이전의 예제 입력은 `output/_archive/cleanup-20261013-150057/`로 이동했다. 새로 실행한 결과를 사용할 때는 명령의 입력을 실제 페이지 JSON 또는 결과 폴더로 바꾼다. 보관 폴더 이름은 이번 컴퓨터의 정리 기록이며 다른 환경에 자동 생성되지 않는다.
