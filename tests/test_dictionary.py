"""합성 고유명사로 입력 검사·Kiwi 품질·재보정의 원문 보존을 확인한다."""

import json
import re

import pytest

from pdf_ocr.dictionary import (
    UserDictionary,
    import_words,
    load_dictionary,
    normalize_words,
    save_dictionary,
    write_local,
)
from pdf_ocr.restore import reprocess, saved_pages
from pdf_ocr.spacing import LocalSpacingRepair


def result(text):
    """좌표 복원이 끝난 합성 단일 문단을 생성한다."""
    return {
        "geometry_applied": True,
        "text": text,
        "paragraphs": [{"text": text, "line_indices": [0]}],
        "reviews": [],
    }


@pytest.fixture(scope="module")
def repairer():
    """공백 포함 이름을 등록한 실제 로컬 Kiwi를 재사용한다."""
    return LocalSpacingRepair(
        UserDictionary("합성 사례", ("하루카", "푸른별 연구소", "아트라펠리스"))
    )


def test_normalization_conflicts_and_empty():
    """중복·공백을 정리하고 충돌 표기·제어 문자·빈 입력을 거부한다."""
    assert normalize_words([" 하루카 ", "", "하루카", "푸른별  연구소"]) == (
        "하루카",
        "푸른별 연구소",
    )
    for words in (["푸른별 연구소", "푸른별연구소"], [""], ["단어\n문장"], [None]):
        with pytest.raises((ValueError, TypeError)):
            normalize_words(words)


def test_utf8_import_save_identity_and_overwrite(tmp_path):
    """BOM TXT·JSON과 식별값을 확인하며 기존 사전과 잘못된 파일을 보호한다."""
    source = tmp_path / "words.txt"
    source.write_text("하루카\n푸른별 연구소\n하루카\n", encoding="utf-8-sig")
    dictionary = UserDictionary("예시", import_words(source))
    path = tmp_path / "dictionary.json"
    save_dictionary(path, dictionary)
    assert load_dictionary(path) == dictionary
    assert load_dictionary(path).identity() == dictionary.identity()
    with pytest.raises(FileExistsError):
        save_dictionary(path, dictionary)
    changed = UserDictionary("수정", ("하루카",))
    save_dictionary(path, changed, overwrite=True)
    assert load_dictionary(path).identity() != dictionary.identity()
    assert dictionary.words == ("하루카", "푸른별 연구소")
    path.write_text('{"version":2,"name":"예시","words":["하루카"]}', encoding="utf-8")
    with pytest.raises(ValueError, match="버전"):
        load_dictionary(path)
    source.write_bytes(b"\xff\xfe")
    with pytest.raises(UnicodeError):
        import_words(source)


def test_export_utf8_and_explicit_replacement(tmp_path):
    """TXT 저장 시 승인 없이 기존 파일을 변경하지 않는다."""
    path = tmp_path / "export.txt"
    write_local(path, "하루카\n")
    with pytest.raises(FileExistsError):
        write_local(path, "변경\n")
    assert path.read_text(encoding="utf-8") == "하루카\n"
    write_local(path, "푸른별 연구소\n", overwrite=True)
    assert path.read_text(encoding="utf-8") == "푸른별 연구소\n"


def test_compound_name_and_particle_improve(repairer):
    """복합 이름·조사 결합을 개선하며 글자와 원시 결과를 보존한다."""
    text = "푸른별연구소에서 하루카를 만났다."
    original = result(text)
    repaired = repairer.repair(original)
    assert repaired["text"] == "푸른별 연구소에서 하루카를 만났다."
    assert repaired["spacing"]["without_dictionary"] != repaired["text"]
    assert re.sub(r"\s", "", repaired["text"]) == re.sub(r"\s", "", text)
    assert original["text"] == text
    assert repaired["spacing"]["dictionary"] == repairer.dictionary.identity()
    assert any(r["reason"] == "dictionary_context_review" for r in repaired["reviews"])


def test_general_sentences_unchanged_in_samples(repairer):
    """합성 일반 문장의 품질이 사전 미적용과 같은지 비교한다."""
    for text, expected in (
        ("운전자는 제조 사에 수리를 요청했다.", "운전자는 제조사에 수리를 요청했다."),
        ("오늘은 날씨가 좋다.", "오늘은 날씨가 좋다."),
    ):
        repaired = repairer.repair(result(text))
        assert repaired["text"] == repaired["spacing"]["without_dictionary"] == expected


def test_split_names_and_paragraphs(repairer):
    """나뉜 이름을 보정하되 문단 경계·줄 식별자는 유지한다."""
    original = result("하루 카는 푸른 별연구소에 갔다.")
    original["paragraphs"].append({"text": "오늘은 날씨가 좋다.", "line_indices": [2]})
    original["text"] += "\n\n오늘은 날씨가 좋다."
    repaired = repairer.repair(original)
    assert len(repaired["paragraphs"]) == 2
    assert "하루카는 푸른별 연구소에" in repaired["text"]
    assert "\n\n오늘은 날씨가 좋다." in repaired["text"]
    assert repaired["paragraphs"][1]["line_indices"] == [2]


def test_overlapping_general_words_require_review():
    """일반 단어·짧은 이름이 겹치는 경우에도 확인 대상으로 남긴다."""
    repair = LocalSpacingRepair(
        UserDictionary("겹침", ("푸른별", "푸른별 연구소", "사랑"))
    )
    repaired = repair.repair(result("푸른별연구소에서 사랑을 연구한다."))
    review = next(
        r for r in repaired["reviews"] if r["reason"] == "dictionary_context_review"
    )
    assert set(review["words"]) == {"푸른별", "푸른별 연구소", "사랑"}
    assert re.sub(r"\s", "", repaired["text"]) == "푸른별연구소에서사랑을연구한다."


def test_missing_geometry_skips_dictionary(repairer):
    """좌표 없는 VLM 결과에는 사전 보정을 적용하지 않는다."""
    original = {
        "geometry_applied": False,
        "text": "하루 카",
        "paragraphs": [],
        "reviews": [],
    }
    assert repairer.repair(original) is original


def page_record(number=1):
    """외부 문서 없이 페이지 기록과 같은 합성 OCR JSON을 생성한다."""
    return {
        "page": number,
        "lines": [
            {
                "text": "푸른별연구소에서 하루카를 만났다.",
                "polygon": [[0, 0], [500, 0], [500, 20], [0, 20]],
                "confidence": 0.9,
            }
        ],
    }


def test_reprocess_preserves_source_and_snapshot(tmp_path, repairer):
    """복수 페이지의 비교 결과·작업 사전을 새 폴더에 저장한다."""
    source = tmp_path / "source"
    source.mkdir()
    for number in (1, 2):
        (source / f"page-{number:03}.json").write_text(
            json.dumps(page_record(number)), encoding="utf-8"
        )
    before = {p.name: p.read_bytes() for p in source.iterdir()}
    output = tmp_path / "new"
    reprocess(source, output, repairer)
    assert before == {p.name: p.read_bytes() for p in source.iterdir()}
    assert "푸른별 연구소" in (output / "combined.txt").read_text(encoding="utf-8")
    assert (output / "without-dictionary.txt").is_file()
    assert load_dictionary(output / "dictionary.json") == repairer.dictionary
    assert len(saved_pages(output)) == 2
    with pytest.raises(FileExistsError):
        reprocess(source, output, repairer)


def test_bad_saved_json_and_duplicate_page(tmp_path):
    """잘못된 입력과 중복 페이지 번호를 거부한다."""
    path = tmp_path / "page-001.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(TypeError):
        saved_pages(path)
    for name in ("page-001.json", "page-002.json"):
        (tmp_path / name).write_text(json.dumps(page_record()), encoding="utf-8")
    with pytest.raises(ValueError, match="페이지 번호"):
        saved_pages(tmp_path)


@pytest.mark.parametrize("options", [[], ["--repair-spacing", "--engine", "vl16"]])
def test_cli_dictionary_rejects_unsupported_options_before_output(
    tmp_path, monkeypatch, options
):
    """사전 옵션의 지원되지 않는 조합은 모델 로드와 출력 생성 전에 거부한다."""
    import sys

    from pdf_ocr import cli

    dictionary = tmp_path / "dictionary.json"
    save_dictionary(dictionary, UserDictionary("예시", ("하루카",)))
    output = tmp_path / "output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ocr",
            "missing.pdf",
            "--dictionary",
            str(dictionary),
            "--output",
            str(output),
            *options,
        ],
    )
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert not output.exists()


def test_line_geometry_split_name_preserves_boundaries(repairer):
    """실제 줄 경계에서 나뉜 합성 이름을 문단 복원 뒤 보정한다."""
    from pdf_ocr.paragraphs import restore_paragraphs

    lines = [
        {"text": "하루", "polygon": [[0, 0], [500, 0], [500, 20], [0, 20]]},
        {
            "text": "카는 푸른별연구소에 갔다.",
            "polygon": [[0, 28], [500, 28], [500, 48], [0, 48]],
        },
    ]
    restored = restore_paragraphs(lines)
    repaired = repairer.repair(restored)
    assert repaired["text"] == "하루카는 푸른별 연구소에 갔다."
    assert repaired["paragraphs"][0]["line_indices"] == [0, 1]
    assert any(r["reason"] == "ambiguous_word_boundary" for r in repaired["reviews"])


def test_reprocess_failure_preserves_completed_pages(tmp_path, repairer):
    """뒤 페이지의 좌표 오류로 실패해도 앞 페이지의 비교 결과는 보존한다."""
    source = tmp_path / "source"
    source.mkdir()
    first = page_record(1)
    second = {"page": 2, "lines": [{"text": "하루 카", "polygon": None}]}
    for record in (first, second):
        (source / f"page-{record['page']:03}.json").write_text(
            json.dumps(record), encoding="utf-8"
        )
    output = tmp_path / "new"
    with pytest.raises(ValueError, match="좌표"):
        reprocess(source, output, repairer)
    assert (output / "page-001.json").is_file()
    assert "푸른별 연구소" in (output / "combined.txt").read_text(encoding="utf-8")
    assert not (output / "page-002.json").exists()
