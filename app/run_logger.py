"""Append-only JSONL run log.

Why JSONL and not xlsx directly: appending a line never touches existing
lines, so a crash costs one partial record instead of the whole workbook.
The Excel report is generated from this file on demand
(see app/log_export.py).

Logging must NEVER break a request. Every failure here is swallowed.
"""

import json
from datetime import datetime, timezone

from app.config import get_settings

# Column order for the Excel export. Keep in sync with what pipeline.py writes.
LOG_FIELDS = [
    "timestamp",
    "request_id",
    "raw_input",
    "preprocessed_input",
    "char_count",
    "script",
    "item_count",
    "items",
    "delivery_location",
    "delivery_date",
    "model",
    "latency_ms",
    "prompt_tokens",
    "completion_tokens",
    "status",
    "error",
    "needs_review",
]


def log_run(record: dict) -> None:
    """Append one record to logs/runs.jsonl. Silently degrades on failure."""
    try:
        settings = get_settings()
        if not settings.log_enabled:
            return

        settings.log_dir.mkdir(parents=True, exist_ok=True)
        path = settings.log_dir / "runs.jsonl"

        payload = {"timestamp": datetime.now(timezone.utc).isoformat()}
        payload.update(record)

        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as exc:  # never break a request because of logging
        print(f"[run_logger] warning: could not write log: {exc}")
