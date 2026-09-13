import json

import pytest
from openpyxl import load_workbook

from app.run_logger import LOG_FIELDS
from app.log_export import export_log

RUN_ONE = {
    "timestamp": "2026-09-08T10:00:00+00:00",
    "request_id": "aaa111",
    "raw_input": "I want 2 kg of Jasmine rice (10kg pack) and 5 boxes of eggs.",
    "preprocessed_input": "I want 2 kg of Jasmine rice (10kg pack) and 5 boxes of eggs.",
    "char_count": 59,
    "script": "latin",
    "item_count": 2,
    "items": [
        {"product_name": "Jasmine rice", "quantity": 2, "unit": "kg", "packing_size": "10kg pack"},
        {"product_name": "eggs", "quantity": 5, "unit": "boxes", "packing_size": None},
    ],
    "delivery_location": None,
    "delivery_date": None,
    "model": "fake-model",
    "latency_ms": 120,
    "prompt_tokens": 1000,
    "completion_tokens": 50,
    "status": "ok",
    "error": None,
    "needs_review": False,
}

RUN_TWO = {
    "timestamp": "2026-09-08T10:01:00+00:00",
    "request_id": "bbb222",
    "raw_input": "我要订购5箱苹果，下星期一送去吉隆坡。",
    "preprocessed_input": "我要订购5箱苹果,下星期一送去吉隆坡。",
    "char_count": 18,
    "script": "cjk",
    "item_count": 1,
    "items": [{"product_name": "苹果", "quantity": 5, "unit": "箱", "packing_size": None}],
    "delivery_location": "吉隆坡",
    "delivery_date": "下星期一",
    "model": "fake-model",
    "latency_ms": 90,
    "prompt_tokens": 1000,
    "completion_tokens": 40,
    "status": "ok",
    "error": None,
    "needs_review": False,
}

RUN_NO_ITEMS = {
    "timestamp": "2026-09-08T10:02:00+00:00",
    "request_id": "ccc333",
    "raw_input": "hello",
    "preprocessed_input": "hello",
    "char_count": 5,
    "script": "latin",
    "item_count": 0,
    "items": [],
    "delivery_location": None,
    "delivery_date": None,
    "model": "fake-model",
    "latency_ms": 80,
    "prompt_tokens": 900,
    "completion_tokens": 10,
    "status": "ok",
    "error": None,
    "needs_review": True,
}


@pytest.fixture
def exported(tmp_path):
    """Write a small log, export it, and hand back the opened workbook."""
    jsonl = tmp_path / "runs.jsonl"
    with open(jsonl, "w", encoding="utf-8") as handle:
        for record in (RUN_ONE, RUN_TWO, RUN_NO_ITEMS):
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    xlsx = tmp_path / "runs.xlsx"
    result = export_log(jsonl_path=jsonl, xlsx_path=xlsx)
    assert result == xlsx
    return load_workbook(xlsx)


def test_workbook_has_both_sheets(exported):
    assert exported.sheetnames == ["Runs", "Items"]


def test_runs_sheet_has_one_row_per_request(exported):
    sheet = exported["Runs"]
    assert sheet.max_row == 1 + 3  # header + 3 runs
    header = [c.value for c in sheet[1]]
    assert header == LOG_FIELDS


def test_items_sheet_has_one_row_per_item(exported):
    """Three runs producing 2 + 1 + 0 items give three item rows."""
    sheet = exported["Items"]
    assert sheet.max_row == 1 + 3


def test_items_from_one_message_share_a_request_id(exported):
    sheet = exported["Items"]
    rows = list(sheet.iter_rows(min_row=2, values_only=True))
    header = [c.value for c in sheet[1]]
    by_name = {row[header.index("product_name")]: row for row in rows}

    assert by_name["Jasmine rice"][header.index("request_id")] == "aaa111"
    assert by_name["eggs"][header.index("request_id")] == "aaa111"
    assert by_name["Jasmine rice"][header.index("packing_size")] == "10kg pack"


def test_mandarin_survives_into_the_cells(exported):
    """The whole point of the utf-8 rules: Excel must show 苹果, not escapes."""
    sheet = exported["Items"]
    header = [c.value for c in sheet[1]]
    rows = list(sheet.iter_rows(min_row=2, values_only=True))
    mandarin = [r for r in rows if r[header.index("request_id")] == "bbb222"][0]

    assert mandarin[header.index("product_name")] == "苹果"
    assert mandarin[header.index("unit")] == "箱"
    assert mandarin[header.index("delivery_location")] == "吉隆坡"
    assert mandarin[header.index("script")] == "cjk"


def test_items_column_is_readable_json_not_escaped(exported):
    sheet = exported["Runs"]
    header = [c.value for c in sheet[1]]
    rows = list(sheet.iter_rows(min_row=2, values_only=True))
    mandarin = [r for r in rows if r[header.index("request_id")] == "bbb222"][0]

    items_cell = mandarin[header.index("items")]
    assert "苹果" in items_cell
    assert "\\u82f9" not in items_cell
    assert json.loads(items_cell)[0]["quantity"] == 5


def test_missing_log_returns_none(tmp_path):
    assert export_log(jsonl_path=tmp_path / "nope.jsonl", xlsx_path=tmp_path / "o.xlsx") is None


def test_empty_log_returns_none(tmp_path):
    jsonl = tmp_path / "runs.jsonl"
    jsonl.write_text("", encoding="utf-8")
    assert export_log(jsonl_path=jsonl, xlsx_path=tmp_path / "o.xlsx") is None


def test_a_corrupt_line_does_not_lose_the_rest_of_the_log(tmp_path):
    """A crash mid-write costs one record, never the whole file."""
    jsonl = tmp_path / "runs.jsonl"
    with open(jsonl, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(RUN_ONE, ensure_ascii=False) + "\n")
        handle.write('{"request_id": "truncated", "items": [\n')  # interrupted write
        handle.write(json.dumps(RUN_TWO, ensure_ascii=False) + "\n")

    xlsx = tmp_path / "runs.xlsx"
    export_log(jsonl_path=jsonl, xlsx_path=xlsx)

    sheet = load_workbook(xlsx)["Runs"]
    assert sheet.max_row == 1 + 2  # the two good records survived


def test_header_row_is_frozen_and_bold(exported):
    """Small thing, but this is a deliverable someone opens in Excel."""
    sheet = exported["Runs"]
    assert sheet.freeze_panes == "A2"
    assert sheet["A1"].font.bold is True
