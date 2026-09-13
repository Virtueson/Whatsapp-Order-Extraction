"""Turn logs/runs.jsonl into a two-sheet Excel report.

Runtime code, not a maintenance script: main.py calls this on server
startup and shutdown and after every one-shot run, so the workbook is
always there without anyone remembering a command.

  Sheet "Runs"  - one row per request
  Sheet "Items" - one row per extracted item, joined by request_id

The Items sheet is what makes the log useful: you can pivot on product
names, spot units the model keeps mishandling, and count how often
quantity comes back as 0.

Debug/manual:  python -m app.log_export
"""

import json
from pathlib import Path

import pandas as pd
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from app.run_logger import LOG_FIELDS

ITEM_COLUMNS = [
    "request_id",
    "timestamp",
    "script",
    "product_name",
    "quantity",
    "unit",
    "packing_size",
    "delivery_location",
    "delivery_date",
]

# Excel cells hard-cap at 32767 characters, and a very wide column is
# unreadable anyway.
_MAX_CELL = 32000
_MAX_COL_WIDTH = 60


def _read_jsonl(path: Path) -> list[dict]:
    """Read the log, skipping any line that is not valid JSON.

    A partial line can only come from an interrupted write, and it must not
    cost us the rest of the log.
    """
    records = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _truncate(value):
    if isinstance(value, str) and len(value) > _MAX_CELL:
        return value[:_MAX_CELL] + "...[truncated]"
    return value


def _autofit_and_freeze(worksheet) -> None:
    """Make the sheet readable on open: sized columns, bold frozen header."""
    for cell in worksheet[1]:
        cell.font = Font(bold=True)
    worksheet.freeze_panes = "A2"

    for column_index, column_cells in enumerate(worksheet.columns, start=1):
        longest = max(
            (len(str(cell.value)) for cell in column_cells if cell.value is not None),
            default=0,
        )
        width = min(max(longest + 2, 10), _MAX_COL_WIDTH)
        worksheet.column_dimensions[get_column_letter(column_index)].width = width


def export_log(jsonl_path: Path | None = None, xlsx_path: Path | None = None) -> Path | None:
    """Write the Excel report. Returns the path, or None when there is nothing to export.

    Both paths default to the configured log directory. They are parameters so
    the function can be tested without touching the real log or needing a .env.
    """
    if jsonl_path is None or xlsx_path is None:
        from app.config import get_settings

        settings = get_settings()
        jsonl_path = jsonl_path or settings.log_dir / "runs.jsonl"
        xlsx_path = xlsx_path or settings.log_dir / "runs.xlsx"

    jsonl_path = Path(jsonl_path)
    xlsx_path = Path(xlsx_path)

    if not jsonl_path.exists():
        return None

    records = _read_jsonl(jsonl_path)
    if not records:
        return None

    # --- Sheet 1: one row per request ---
    runs_rows = []
    for record in records:
        row = {field: _truncate(record.get(field)) for field in LOG_FIELDS}
        # items is a list; Excel needs one cell, so store it as readable JSON.
        row["items"] = _truncate(
            json.dumps(record.get("items") or [], ensure_ascii=False)
        )
        runs_rows.append(row)
    runs_df = pd.DataFrame(runs_rows, columns=LOG_FIELDS)

    # --- Sheet 2: one row per extracted item ---
    item_rows = []
    for record in records:
        for item in record.get("items") or []:
            item_rows.append(
                {
                    "request_id": record.get("request_id"),
                    "timestamp": record.get("timestamp"),
                    "script": record.get("script"),
                    "product_name": item.get("product_name"),
                    "quantity": item.get("quantity"),
                    "unit": item.get("unit"),
                    "packing_size": item.get("packing_size"),
                    "delivery_location": record.get("delivery_location"),
                    "delivery_date": record.get("delivery_date"),
                }
            )
    items_df = pd.DataFrame(item_rows, columns=ITEM_COLUMNS)

    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        runs_df.to_excel(writer, sheet_name="Runs", index=False)
        items_df.to_excel(writer, sheet_name="Items", index=False)
        for sheet in writer.book.worksheets:
            _autofit_and_freeze(sheet)

    return xlsx_path


if __name__ == "__main__":
    from app.console import enable_utf8_output

    enable_utf8_output()
    path = export_log()
    if path is None:
        print("Nothing to export - logs/runs.jsonl is missing or empty.")
    else:
        print(f"Wrote {path}")
