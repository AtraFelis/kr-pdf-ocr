# 문서 안내

문서 내용의 주된 목적에 따라 저장한다. 프로젝트 공통 규칙과 문서 우선순위는 [AGENTS.md](../AGENTS.md)를 따른다.

## 기획과 기능 사용법

`docs/`에는 현재 요구사항·작업 목록·기능 사용법을 둔다.

- [기획서](PLAN.md)
- [개발 목록](TASKS.md)
- [데스크톱 사용법](DESKTOP_APP.md)
- [페이지·영역 선택](PAGE_SELECTION.md)
- [문단 복원·띄어쓰기 보정](TEXT_RESTORATION.md)
- [짧은 대사·문장부호 재인식](SHORT_TEXT_RETRY.md)
- [고유명사 사용자 사전 사용법](USER_DICTIONARY.md)
- [Markdown 사용법·전용 환경](MARKDOWN_EXPORT.md)
- [모델 안내·출력 형식 설계](MODEL_AND_EXPORT.md)
- [GitHub 저장소 설명](GITHUB_DESCRIPTION.md)

## 개발 규칙

`docs/rules/`에는 코딩 컨벤션, Git 작업 규칙, 개발 절차처럼 개발 중 지켜야 하는 규칙을 둔다.

- [Git 컨벤션](rules/GIT_CONVENTIONS.md)
- [코딩 컨벤션·Docstring](rules/CODING_CONVENTIONS.md)
- 프로젝트 전체의 코딩 컨벤션·금지 사항·검증 기준은 루트 [AGENTS.md](../AGENTS.md)에 정의한다.

## 개발 기록

`docs/history/`에는 모델 선택 근거, 환경 구성 이력, 실험·검증 결과, 발견한 오류와 당시의 한계를 둔다.

- [OCR 실행 환경·샘플 시험 기록](history/OCR_SETUP.md)
- [OCR 모델 선택 기록](history/MODEL_SELECTION.md)
- [기능 구현·검증 기록](history/IMPLEMENTATION_LOG.md)
- [고유명사 사용자 사전 도입 결정](history/USER_DICTIONARY_DECISION.md)
- [Markdown 샘플 실행·미리보기 검증](history/MARKDOWN_SAMPLE_VALIDATION.md)
- [PR #8 CodeRabbit 리뷰 반영](history/CODERABBIT_PR8.md)
- [한국어 문자 교정 도입 계획](history/TEXT_CORRECTION_PLAN.md)
- [오류 샘플의 보정 중단 수정](history/OCR_ERROR_SAMPLE.md)
- [인용문 여는 부호의 공백 수정](history/QUOTE_SPACING.md)
- [짧은 대사·문장부호 재인식 검증](history/SHORT_TEXT_RETRY.md)
- [실제 짧은 대사 오류의 VLM 재인식](history/VISUAL_RETRY_ERRORS.md)
- [구조화 Markdown 첫 연결 기록](history/STRUCTURED_MARKDOWN_IMPLEMENTATION.md)
- [모델 정보 아이콘 구현 기록](history/MODEL_INFO_IMPLEMENTATION.md)
- [사용자 사전 구현·품질 확인](history/USER_DICTIONARY_IMPLEMENTATION.md)
- [작업 완료 PR·Docstring 규칙 적용](history/DOCSTRING_RULES.md)

기능 사용법에는 현재 동작과 제한을 설명하고, 과거 실행 결과는 기록 문서로 연결한다. 기록을 작성할 때 실행 조건과 실제 확인 범위를 적는다. 실제 PDF·OCR 결과·로그는 기존 추적 제외 폴더에 보관한다. 문서를 이동하면 README·AGENTS.md와 문서 사이의 상대 링크도 함께 수정한다.
