# 한국어 문자 교정 평가

`gec_kr`은 현재 **평가 전용**이다. 앱의 OCR·Kiwi·사전 보정에 자동 연결하지 않는다. 2026-10-13 합성 자료의 CPU/GPU 결과에서 일부 오류 개선과 정상 문장 변경을 함께 확인해 제품 도입을 보류했다. [실행 결과와 판단](history/GEC_EVALUATION.md)을 따른다.

## 로컬 실행

프로젝트 루트의 PowerShell에서 `.venv`를 사용한다. 현재 잠금 환경의 PyTorch 2.9.1·Transformers 5.19.0·Kiwi 0.24.0으로 확인했고 의존성은 추가하지 않았다.

```powershell
# 모델만 다운로드: 네트워크 필요, 사용자 문서를 읽지 않음
.\.venv\Scripts\python.exe scripts/download_gec_model.py
# 설치 후 CPU/GPU 비교: 존재하지 않는 새 출력 폴더 지정
.\.venv\Scripts\python.exe scripts/evaluate_gec.py --device cpu --output "output/gec-cpu-$(Get-Date -Format yyyyMMdd-HHmmss)"
.\.venv\Scripts\python.exe scripts/evaluate_gec.py --device gpu --output "output/gec-gpu-$(Get-Date -Format yyyyMMdd-HHmmss)"
```

GPU를 명시했는데 CUDA를 사용할 수 없으면 오류를 낸다. 모델은 `models/gec_kr/`의 고정 리비전과 내장 모델 코드만 읽는다. 문서 처리 경로와 다운로드 스크립트는 분리했다. 평가에서는 오프라인 플래그와 Python 소켓 연결 거부를 사용하며 OS 방화벽 수준의 검증은 아니다.

## 자료와 보고서

기본 자료는 [직접 작성한 합성 사례 20개](../samples/synthetic/gec_cases.json)다. 실제 PDF나 소설의 본문은 포함하지 않는다. `--cases 로컬JSON경로`로 같은 형식의 자료를 지정할 수 있다. 항목은 고유한 `id`, `category`, 비어 있지 않은 `source`·`reference`, 선택적인 `protected` 문자열 목록이며 보호 문자열은 원문에 존재해야 한다.

- 비교 경로: 원시 입력, Kiwi 단독, gec_kr 단독, Kiwi 후 gec_kr. Kiwi는 사전 없는 `space(reset_whitespace=True)`이며 앱 전체 문단 복원·사전 경로의 평가가 아니다.
- `cases.json`: 입력·정답·경로별 후보/실패·시간·원문 대비 변경 위치·CER·보호 표기 손실. 변경 위치는 Python Unicode 코드 포인트의 `[start, end)`이며 Qt UTF-16 위치로 직접 사용하지 않는다.
- `report.json`: 출처·리비전·환경·FP32 생성 조건·집계·시간·메모리. 파일 덮어쓰기는 거부하며 추론 중 완료 사례를 저장한다. 실행이 중단되면 최종 보고서는 없을 수 있다.
- CER은 공백 정규화/제거 두 조건으로 계산한다. 성공 후보만의 지표와 실패 시 원문을 유지한 전체 사례 지표를 분리한다. 서로 다른 분모의 CER을 직접 비교하지 않는다. 문단 경계 품질을 측정하지 않는다.
- 정상 문장 변경은 과잉 교정의 검토 대상이며 모두 문법 오류라는 뜻은 아니다. 보호 표기 손실은 정확한 문자열이 사라졌다는 뜻으로 공백 분리도 포함한다. 사전 강제 보호 기능은 아니다.

짧은 대사·누락 문장부호의 정답은 원본 자료를 바탕으로 판단해야 한다. 문맥이 없는 `ac`나 누락 마침표를 텍스트 모델이 반드시 회복할 수 있다고 가정하지 않는다.

## 현재 제한

공식 모델 카드·파일 목록에서 명시적인 라이선스를 확인하지 못했다. 로컬에 평가용 모델을 받았지만 앱 배포본 포함·재배포·제품 사용 조건이 확인된 것으로 표현하지 않는다. CPU/GPU FP32와 공식 예제 생성 조건 한 종류를 비교했으며 추가 디코딩 설정·실제 PDF·장문·다양한 고유명사·정밀 성능 측정은 미평가다. 정상 문장과 고유명사를 변경할 수 있으므로 자동 치환에 사용하지 않는다.

## KoGEC 추가 확인과 제한된 진단

KoGEC 공개 600M/3.3B는 모델과 토크나이저 크기가 2개 다르고 논문의 교정 토큰 매핑이 빠져 있다. 정식 교정 성능 평가·앱 연결을 보류하며 [확인 기록](history/KOGEC_CHECKPOINT.md)을 따른다. `probe_kogec.py`는 `--diagnostic-only`를 명시한 한국어→한국어 GPU 진단만 허용한다. 공식 명령은 [AGENTS.md](../AGENTS.md)에 있다. 600M은 FP32, 3.3B는 FP16으로 실행하며 일반 CPU/GPU 자동 전환을 제공하지 않는다.

추가 합성 10개는 [별도 자료](../samples/synthetic/gec_extra_cases.json)로 보관한다. 기존 20개와 합칠 때 id 중복을 피한다. 실제 OCR/정답 자료는 로컬에만 저장하고 Git에 추가하지 않는다. 진단 `report.json`은 `official_quality_evaluation=false`이며 알려진 `kor_Hang` 토큰을 입력·출력에 사용하는 제어 조건이다. 누락 ID를 추측해서 채우거나 진단 CER을 모델 순위·논문 재현 결과로 사용하지 않는다.
