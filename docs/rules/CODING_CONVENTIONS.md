# 코딩 컨벤션과 Docstring 규칙

[AGENTS.md](../../AGENTS.md)의 코딩 컨벤션·금지 사항·문서 우선순위를 따른다. Git 작업 완료와 PR 절차는 [Git 컨벤션](GIT_CONVENTIONS.md)을 따른다.

## 필수 적용 범위

- 코드를 작성·수정할 때 docstring을 반드시 작성하거나 실제 동작에 맞춰 갱신한다.
- `src/**/*.py`, `scripts/**/*.py`, `tests/**/*.py`의 모듈·클래스·함수·메서드에 적용한다.
- 비공개·중첩 정의·생성자·특수 메서드·Qt 이벤트·테스트·대역과 보조 함수도 포함한다. 빈 설명·이름만 되풀이하는 설명은 허용하지 않는다.
- 외부 라이브러리·가상환경·생성 캐시는 검사 대상이 아니다. 간단한 람다는 문맥이 분명해야 하며 복잡한 로직은 이름 있는 함수로 분리해 문서화한다.
- `.bat`처럼 docstring 문법이 없는 실행 파일은 역할을 설명하는 문서 주석을 작성한다.

## 작성 내용과 형식

- Python은 선언 본문의 첫 문장에 삼중 큰따옴표 문자열을 둔다. 짧은 함수는 구체적인 역할을 한 줄로 설명한다.
- 새 설명은 한국어를 기본으로 하며 기존의 유효한 영문 설명은 유지할 수 있다. 복잡한 함수는 Google 형식의 `Args`, `Returns`/`Yields`, `Raises`를 필요한 만큼 사용한다.
- 입력 형식·좌표의 기준/단위·부작용·파일 덮어쓰기·원본 보존·소유한 자원 해제 등 호출자가 알아야 할 조건을 적는다. 반환하지 않는 값을 반환한다고 적거나 제공되지 않는 신뢰도를 보장하지 않는다.
- 주석은 처리 이유, docstring은 호출 계약과 역할을 설명한다. 이름·타입 선언을 단순히 복제하지 않으며 아직 구현하지 않은 기능을 현재 동작으로 설명하지 않는다.

```python
def values(self):
    """왼쪽·위쪽·오른쪽·아래쪽 순서의 상대 좌표 목록을 반환한다."""
    return [self.left, self.top, self.right, self.bottom]
```

위 코드는 현재 영역 객체의 형식 예시다. 실제 저장 구조와 반환 동작을 확인해 설명을 작성한다.

## 확인

프로젝트 루트에서 등록된 명령을 사용한다.

```powershell
.\.venv\Scripts\python.exe scripts/check_docstrings.py
.\.venv\Scripts\python.exe -m ruff check src scripts tests
.\.venv\Scripts\python.exe -m ruff format --check src scripts tests
```

AST 검사로 비공개·중첩 정의와 비어 있는 docstring까지 확인하고 Ruff로 공개 선언의 누락을 함께 확인한다. 설명의 정확성은 관련 코드와 대조해 검토한다. Docstring·주석만 추가한 기존 코드에는 실행 구문 변경 여부도 확인하고, 테스트·실행을 수행하지 않았다면 그 범위와 이유를 기록한다.
