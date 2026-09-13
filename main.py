"""Composition root.

This file WIRES things together. It contains no business logic.

Two ways to run:
    python main.py                    -> start the API server
    python main.py --text "20kg rice" -> one-shot extraction, no server

Either way you end up with BOTH log files: logs/runs.jsonl (appended as
requests come in) and logs/runs.xlsx (regenerated on start and stop, and
after each one-shot run). Nothing to remember, and no per-request cost.
"""

import argparse
import json
import sys
from contextlib import asynccontextmanager

import uvicorn

from app.api import create_app
from app.console import enable_utf8_output
from app.log_export import export_log


def refresh_excel_report(reason: str) -> None:
    """Regenerate logs/runs.xlsx from the JSONL log.

    Never raises. A failure to write a report must not stop the server from
    starting, or stop it from shutting down cleanly.

    Messages go to stderr, not stdout: `main.py --text "..." > out.json` must
    produce clean JSON, and these notices would corrupt it.
    """
    try:
        path = export_log()
        if path is None:
            print(f"[export] {reason}: no log entries yet, nothing to write", file=sys.stderr)
        else:
            print(f"[export] {reason}: wrote {path}", file=sys.stderr)
    except Exception as exc:
        print(f"[export] {reason}: could not write the Excel report: {exc}", file=sys.stderr)


@asynccontextmanager
async def lifespan(app):
    """Refresh the Excel report when the server starts and again when it stops.

    Chosen over exporting on every request: openpyxl rewrites the whole
    workbook each time, so per-request export would slow down as the log grows
    and would need a lock to stay safe under concurrency. Appending to the
    JSONL is what happens per request; the workbook is derived from it.

    A hard kill (rather than Ctrl+C) skips the shutdown export. Run
    `python -m app.log_export` to catch up.
    """
    refresh_excel_report("startup")
    yield
    refresh_excel_report("shutdown")


# Module-level so `uvicorn main:app --reload` works too.
app = create_app(lifespan=lifespan)


def main() -> None:
    enable_utf8_output()

    parser = argparse.ArgumentParser(description="WhatsApp order extraction service")
    parser.add_argument("--text", help="Run one extraction and exit. No server started.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes.")
    args = parser.parse_args()

    if args.text:
        from app.pipeline import run

        result, meta = run(args.text)
        # Result on stdout so it can be piped; diagnostics on stderr so they don't
        # pollute the JSON. `python main.py --text "..." > out.json` gives clean JSON.
        print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
        print("--- meta ---", file=sys.stderr)
        print(
            json.dumps(meta.model_dump(), ensure_ascii=False, indent=2),
            file=sys.stderr,
        )
        refresh_excel_report("one-shot run")
        return

    print(f"Docs: http://{args.host}:{args.port}/docs")
    uvicorn.run(
        "main:app" if args.reload else app,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
