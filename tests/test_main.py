"""Tests for the composition root's wiring.

main.py holds no business logic, but it does decide WHEN the Excel report is
regenerated. That decision is worth pinning down: if the lifespan hook stops
firing, nobody notices until they open a stale workbook.
"""

from fastapi.testclient import TestClient

import main


def test_report_is_refreshed_on_startup_and_shutdown(monkeypatch, tmp_path):
    """TestClient as a context manager runs the real lifespan, so this
    exercises the same code path as Ctrl+C on a live server."""
    calls = []

    def fake_export_log():
        calls.append("exported")
        return tmp_path / "runs.xlsx"

    monkeypatch.setattr(main, "export_log", fake_export_log)

    with TestClient(main.app):
        # Startup has run by now; shutdown has not.
        assert calls == ["exported"]

    # Leaving the block triggers shutdown.
    assert calls == ["exported", "exported"]


def test_a_failed_export_does_not_stop_the_server_starting(monkeypatch):
    """An unwritable workbook - Excel has it open, disk is full - must not
    take the service down. Verified for real: with runs.xlsx open in Excel the
    export fails with PermissionError and extraction carries on."""

    def boom():
        raise PermissionError("[Errno 13] Permission denied: runs.xlsx")

    monkeypatch.setattr(main, "export_log", boom)

    with TestClient(main.app) as client:
        response = client.get("/health")
        assert response.status_code in (200, 503)  # reachable either way


def test_an_empty_log_is_reported_not_treated_as_an_error(monkeypatch, capsys):
    """export_log returns None when there is nothing to export yet."""
    monkeypatch.setattr(main, "export_log", lambda: None)

    main.refresh_excel_report("test")

    assert "no log entries yet" in capsys.readouterr().err


def test_export_notices_go_to_stderr_never_stdout(monkeypatch, tmp_path, capsys):
    """`main.py --text "..." > out.json` must produce clean JSON, so these
    notices must not land on stdout."""
    monkeypatch.setattr(main, "export_log", lambda: tmp_path / "runs.xlsx")

    main.refresh_excel_report("one-shot run")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "wrote" in captured.err
