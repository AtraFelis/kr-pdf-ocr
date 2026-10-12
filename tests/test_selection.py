import json
import sys

import pytest
from pypdf import PdfWriter

from pdf_ocr import cli
from pdf_ocr.pdf import page_count, render_pages
from pdf_ocr.selection import Region, load_regions, page_coordinates, select_pages


def make_pdf(path, count=3, rotation=0):
    writer = PdfWriter()
    for _ in range(count):
        page = writer.add_blank_page(width=600, height=1000)
        if rotation:
            page.rotate(rotation)
    writer.write(path)
    return path


def test_page_order_ranges_and_exclusions():
    assert select_pages("3,1-2,2", "2", 3) == [1, 3]
    assert select_pages("all", "1,3", 3) == [2]


@pytest.mark.parametrize(
    "selection,excluded",
    [("all", "1-3"), ("4", ""), ("1-999999999", ""), ("1", "4"), ("3-1", "")],
)
def test_invalid_selection_and_empty_result(selection, excluded):
    with pytest.raises(ValueError):
        select_pages(selection, excluded, 3)


def test_pixel_region_is_resolution_independent():
    region = Region.from_pixels([0, 200, 1000, 800], 1000, 1000)
    assert region.values() == [0, 0.2, 1, 0.8]
    assert region.pixel_box(1000, 1000) == (0, 200, 1000, 800)
    assert region.pixel_box(2000, 3000) == (0, 600, 2000, 2400)


@pytest.mark.parametrize(
    "values",
    [
        (0, 0, 0, 1),
        (0, 0.8, 1, 0.2),
        (-0.1, 0, 1, 1),
        (0, 0, 1.1, 1),
        (0, float("nan"), 1, 1),
        (False, 0, 1, 1),
    ],
)
def test_invalid_regions(values):
    with pytest.raises(ValueError):
        Region(*values)


def test_page_regions_validate_and_override(tmp_path):
    path = tmp_path / "regions.json"
    path.write_text(json.dumps({"1": [0, 0.2, 1, 0.8]}), encoding="utf-8")
    assert load_regions(path, 2)[1] == Region(0, 0.2, 1, 0.8)
    path.write_text('{"3":[0,0,1,1]}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_regions(path, 2)


def test_translate_coordinates_and_preserve_raw_geometry():
    original = [
        {
            "text": "본문",
            "polygon": [[0, 0], [20, 0], [20, 10], [0, 10]],
            "confidence": 0.9,
        }
    ]
    [result] = page_coordinates(original, (100, 200, 400, 800), 1000, 1000)
    assert result["polygon"][0] == [100, 200]
    assert result["relative_polygon"][2] == [0.12, 0.21]
    assert result["polygon_in_input"] == original[0]["polygon"]
    assert original[0]["polygon"][0] == [0, 0]
    assert (
        page_coordinates([{"text": "본문", "polygon": None}], (0, 0, 1, 1), 1, 1)[0][
            "relative_polygon"
        ]
        is None
    )


def test_rotated_pdf_uses_display_coordinates(tmp_path):
    path = make_pdf(tmp_path / "rotated.pdf", 1, 90)
    assert page_count(path) == 1
    [(number, image)] = list(render_pages(path, [1], 72))
    assert number == 1 and image.size == (1000, 600)
    assert Region(0, 0.2, 1, 0.8).pixel_box(*image.size) == (0, 120, 1000, 480)
    image.close()


@pytest.mark.parametrize("page_override", [False, True])
def test_cli_crops_before_ocr_and_combines_only_selected_pages(
    tmp_path, monkeypatch, page_override
):
    path = make_pdf(tmp_path / "input.pdf")
    output = tmp_path / "output"
    calls = []

    class Engine:
        def __init__(self, root, device="cpu"):
            pass

        def recognize(self, image):
            calls.append(image.size)
            return [
                {
                    "text": "본문",
                    "confidence": 0.9,
                    "polygon": [[0, 0], [20, 0], [20, 10], [0, 10]],
                }
            ]

    monkeypatch.setattr(cli, "LocalPaddleEngine", Engine)
    monkeypatch.setattr(cli.socket.socket, "connect", cli.socket.socket.connect)
    monkeypatch.setattr(cli.socket.socket, "connect_ex", cli.socket.socket.connect_ex)
    arguments = [
        "ocr",
        str(path),
        "--pages",
        "1-3",
        "--exclude-pages",
        "1,3",
        "--dpi",
        "72",
        "--y-range",
        "200,800",
        "--output",
        str(output),
    ]
    if page_override:
        overrides = tmp_path / "regions.json"
        overrides.write_text('{"2":[0,0.2,1,0.8]}', encoding="utf-8")
        # This page-specific region overrides the global full-height choice.
        arguments[arguments.index("200,800")] = "0,1000"
        arguments.extend(["--regions-file", str(overrides)])
    monkeypatch.setattr(sys, "argv", arguments)
    cli.main()
    assert calls == [(600, 600)]
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["selected_pages"] == [2]
    record = summary["completed_pages"][0]
    assert record["region_pixel_box"] == [0, 200, 600, 800]
    assert record["lines"][0]["polygon"][0] == [0, 200]
    assert (output / "combined.txt").read_text(encoding="utf-8").strip() == "본문"
    assert not (output / "page-001.txt").exists()
    assert (output / "page-002-selection.png").exists()


def test_empty_selection_fails_before_model_load_or_output_creation(
    tmp_path, monkeypatch
):
    path = make_pdf(tmp_path / "input.pdf", 1)
    output = tmp_path / "output"
    monkeypatch.setattr(
        sys, "argv", ["ocr", str(path), "--exclude-pages", "1", "--output", str(output)]
    )
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2 and not output.exists()


def test_multiple_selected_pages_combined_in_pdf_order(tmp_path, monkeypatch):
    path = make_pdf(tmp_path / "input.pdf")
    output = tmp_path / "output"

    class Engine:
        def __init__(self, root, device="cpu"):
            self.calls = 0

        def recognize(self, image):
            self.calls += 1
            return [{"text": f"결과{self.calls}", "polygon": None}]

    monkeypatch.setattr(cli, "LocalPaddleEngine", Engine)
    monkeypatch.setattr(cli.socket.socket, "connect", cli.socket.socket.connect)
    monkeypatch.setattr(cli.socket.socket, "connect_ex", cli.socket.socket.connect_ex)
    monkeypatch.setattr(
        sys,
        "argv",
        ["ocr", str(path), "--pages", "3,1,1", "--dpi", "72", "--output", str(output)],
    )
    cli.main()
    assert (output / "combined.txt").read_text(encoding="utf-8") == "결과1\n\n결과2\n"
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["selected_pages"] == [1, 3]


def test_encrypted_pdf_reports_open_error(tmp_path):
    path = tmp_path / "encrypted.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("example-password")
    writer.write(path)
    with pytest.raises(ValueError, match="PDF를 열 수 없습니다"):
        page_count(path)
