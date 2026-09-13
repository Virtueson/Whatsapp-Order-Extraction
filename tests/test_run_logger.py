import json

import pytest

from app.run_logger import LOG_FIELDS, log_run


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    """Point the logger at a temp directory instead of the real logs/."""
    import app.run_logger as module

    class FakeSettings:
        log_enabled = True
        log_dir = tmp_path

    monkeypatch.setattr(module, "get_settings", lambda: FakeSettings())
    return tmp_path


def test_log_fields_start_with_timestamp():
    """export_log.py builds its Runs sheet from this order."""
    assert LOG_FIELDS[0] == "timestamp"
    assert "request_id" in LOG_FIELDS
    assert "needs_review" in LOG_FIELDS


def test_writes_one_json_line_per_call(log_dir):
    log_run({"request_id": "a1", "raw_input": "first"})
    log_run({"request_id": "b2", "raw_input": "second"})

    lines = (log_dir / "runs.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["request_id"] == "a1"
    assert json.loads(lines[1])["raw_input"] == "second"
    assert "timestamp" in json.loads(lines[0])


def test_mandarin_is_written_readable_not_escaped(log_dir):
    """ensure_ascii=False, checked at the byte level so there is no ambiguity."""
    log_run({"request_id": "c3", "raw_input": "我要订购5箱苹果"})

    raw_bytes = (log_dir / "runs.jsonl").read_bytes()
    assert "苹果".encode("utf-8") in raw_bytes
    # The \uXXXX escape form ensure_ascii=True would have produced.
    assert b"\\u82f9" not in raw_bytes


def test_logging_disabled_writes_nothing(tmp_path, monkeypatch):
    import app.run_logger as module

    class FakeSettings:
        log_enabled = False
        log_dir = tmp_path

    monkeypatch.setattr(module, "get_settings", lambda: FakeSettings())

    log_run({"request_id": "d4"})
    assert not (tmp_path / "runs.jsonl").exists()


def test_a_logging_failure_never_raises(monkeypatch):
    """A request must succeed even if the log cannot be written."""
    import app.run_logger as module

    def boom():
        raise OSError("disk full")

    monkeypatch.setattr(module, "get_settings", boom)
    log_run({"request_id": "e5"})  # must not raise
