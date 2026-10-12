# 문단 복원과 로컬 띄어쓰기 보정

## 현재 동작

OCR 원본 줄과 좌표를 보존하고, 단일 본문 영역의 줄을 위에서 아래로 정렬한다. 대표 줄 높이·줄 간격·들여쓰기·짧은 마지막 줄·글자 크기 변화와 목록 표식을 이용해 문단을 구분한다. 문장 마침표만으로 문단을 끊지 않는다. 문단 사이에는 빈 줄을 넣는다.

한국어 뒤에 조사만 이어지는 등 명확한 규칙에 해당하면 공백 없이 연결한다. 그 밖의 한국어·영어 단어 경계는 공백으로 연결하고 `ambiguous_word_boundary`로 표시한다. OCR이 잃어버린 문자나 문장부호는 생성하지 않는다.

좌표가 없으면 텍스트의 기존 문단 형태를 보존하고 `missing_geometry`로 표시한다. 같은 높이에 여러 영역이 겹치면 읽기 순서를 추측하지 않고 기존 순서를 보존해 `overlapping_rows_or_columns`로 표시한다. 다단 편집·표·회전 문서·복잡한 각주는 지원 품질을 보장하지 않는다.

## 선택적 띄어쓰기 보정

`--repair-spacing`은 Kiwi 0.24.0과 kiwipiepy_model 0.24.0을 로컬에서 사용한다. 모델은 설치 패키지에 포함되며 실행 중 다운로드하지 않는다. 각 문단에 `Kiwi.space(reset_whitespace=True)`를 적용한다.

공백을 제거한 보정 전후 문자열이 완전히 같아야 적용한다. 글자가 달라지면 오류로 중단한다. 변경된 문단은 `spacing_suggestion`에 전후 텍스트를 기록한다. 기존 모호한 연결 표시도 유지한다. 따라서 이 결과는 확인 가능한 제안이며 고유명사·문학적 표현의 정확성을 보장하지 않는다.

패키지 배포 라이선스와 고지는 앱 패키징 시 검토한다. API 출처: https://bab2min.github.io/kiwipiepy/

## 실행

프로젝트 루트의 PowerShell에서 새 출력 폴더를 지정한다.

```powershell
# OCR부터 문단 복원과 띄어쓰기 보정까지
.\.venv\Scripts\python.exe -m pdf_ocr.cli samples/input/sample.pdf --pages 1-2 --repair-spacing --output "output/paragraphs-$(Get-Date -Format yyyyMMdd-HHmmss)"
# 저장한 JSON만 재처리
.\.venv\Scripts\python.exe -m pdf_ocr.restore output/ocr-run-02/page-001.json --repair-spacing --output "output/reprocess-$(Get-Date -Format yyyyMMdd-HHmmss)"
```

재처리 도구는 PDF나 OCR 모델을 다시 열지 않는다. 기본 OCR 명령은 문단 복원만 적용하고 Kiwi 보정은 명시적으로 선택한다. `--keep-line-breaks`와 `--repair-spacing`은 함께 사용할 수 없다.

원시 TXT·줄 JSON은 그대로 남기고 최종 TXT에는 문단 결과를 저장한다. 페이지 JSON의 `restoration`은 최종 텍스트, 문단별 원시 줄 인덱스, 확인 항목과 좌표 처리 여부를 담는다. `summary.json`에는 요청한 복원·보정 옵션을 기록한다. 좌표 없는 페이지는 복원 옵션이 켜져 있어도 `geometry_applied=false`이며 별도 문단 재구성을 수행하지 않는다.

## 검증 결과와 제한

샘플 첫 페이지는 제목과 하단 쪽수를 포함한 7개 문단으로 구분했다. `output/paragraph-run-01`은 규칙 기반 복원, `output/paragraph-spacing-01`은 선택적 보정을 추가한 결과다. 한자 병기를 같은 방식으로 제외한 정답 초안 비교에서 공백 포함 오류율은 원시 결과 약 15.79%에서 보정 결과 약 3.09%로 감소했다. 공백 무시 오류율은 둘 다 약 1.92%였다.

이는 한 페이지에 대한 결과이며 연속 공백을 한 칸으로 정규화한 문자 편집 거리다. 문단 경계 정확도나 일반적인 OCR 정확도를 뜻하지 않는다. 원래 OCR의 문자·문장부호 오류는 그대로 남았다.

페이지 사이 문단 연결, 사용자가 확인 항목을 수정하는 화면, 단어 경계 완전 자동 판정과 표·다단 처리는 후속 작업이다. 현재 문단 경계는 휴리스틱이므로 원문 미리보기와 대조해야 한다.
