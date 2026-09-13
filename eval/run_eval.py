"""Score the pipeline against eval/golden.jsonl.

This is a SCRIPT, not a pytest test, because it costs money and needs a
real API key. Tests in tests/ must always run offline. The pure scoring
functions here ARE covered by tests/test_run_eval.py.

Read the numbers with the tags in mind:

  spec        - the 7 worked examples from the exercise brief. These are the
                contract. Anything below 100% here is a real problem, since
                they are also the few-shot examples.
  regression  - cases whose expected output was verified by hand against the
                spec rules and then locked in. High scores here are NOT
                evidence of blind accuracy; they catch a prompt change that
                breaks behaviour that used to work.
  adversarial - expected outputs written from the spec rules WITHOUT running
                them first. This is the honest accuracy signal.

Usage:
    python -m eval.run_eval                 # everything
    python -m eval.run_eval --tag spec      # just the contract cases
    python -m eval.run_eval --id spec-6-list-form
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from app.config import PROJECT_ROOT
from app.pipeline import run

GOLDEN_PATH = PROJECT_ROOT / "eval" / "golden.jsonl"
RESULTS_DIR = PROJECT_ROOT / "eval"

ITEM_FIELDS = ["product_name", "quantity", "unit", "packing_size"]
ORDER_FIELDS = ["delivery_location", "delivery_date"]


def same(a, b) -> bool:
    """Lenient equality: None==None, numbers numerically, strings case-insensitively.

    Case-insensitive because "Penang" and "penang" are the same answer for
    order processing; a difference in casing is not an extraction error.
    """
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    return str(a).strip().lower() == str(b).strip().lower()


def score_case(expected: dict, actual: dict) -> dict:
    """Compare one expected/actual pair. Returns counters plus per-field hits.

    Items are compared positionally: the model should list them in the order
    they appear in the message. Item fields are only scored for positions
    present in BOTH lists, so a missing item costs item_count_match rather
    than silently dragging every field down.
    """
    exp_items = expected.get("items") or []
    act_items = actual.get("items") or []

    scores: dict = {
        "item_count_match": len(exp_items) == len(act_items),
        "expected_items": len(exp_items),
        "actual_items": len(act_items),
    }

    for field in ORDER_FIELDS:
        scores[field] = same(expected.get(field), actual.get(field))

    compared = min(len(exp_items), len(act_items))
    for field in ITEM_FIELDS:
        hits = sum(
            1
            for i in range(compared)
            if same(exp_items[i].get(field), act_items[i].get(field))
        )
        scores[f"{field}_hits"] = hits
        scores[f"{field}_total"] = compared

    scores["exact_match"] = (
        scores["item_count_match"]
        and all(scores[f] for f in ORDER_FIELDS)
        and all(scores[f"{f}_hits"] == compared for f in ITEM_FIELDS)
    )
    return scores


def results_path(tag: str | None = None, case_id: str | None = None) -> Path:
    """Where this run's spreadsheet goes.

    A filtered run must NOT overwrite the full report: `--tag spec` writing
    7 rows over a 25-case results.xlsx would silently destroy the number you
    are about to quote in the write-up.
    """
    if case_id:
        return RESULTS_DIR / f"results-{case_id}.xlsx"
    if tag:
        return RESULTS_DIR / f"results-{tag}.xlsx"
    return RESULTS_DIR / "results.xlsx"


def load_cases(tag: str | None = None, case_id: str | None = None) -> list[dict]:
    cases = [
        json.loads(line)
        for line in GOLDEN_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if tag:
        cases = [c for c in cases if tag in c.get("tags", [])]
    if case_id:
        cases = [c for c in cases if c["id"] == case_id]
    return cases


def _field_accuracy(frame: pd.DataFrame, field: str) -> tuple[int, int]:
    hits = int(frame[f"{field}_hits"].sum())
    total = int(frame[f"{field}_total"].sum())
    return hits, total


def _print_block(title: str, frame: pd.DataFrame) -> None:
    if frame.empty:
        return
    total = len(frame)
    print()
    print(f"{title}  ({total} cases)")
    print("-" * 62)
    print(f"  {'exact_match':<24} {int(frame['exact_match'].sum()):>4}/{total:<5} {frame['exact_match'].mean():>7.1%}")
    print(f"  {'item_count_match':<24} {int(frame['item_count_match'].sum()):>4}/{total:<5} {frame['item_count_match'].mean():>7.1%}")
    for field in ORDER_FIELDS:
        print(f"  {field:<24} {int(frame[field].sum()):>4}/{total:<5} {frame[field].mean():>7.1%}")
    for field in ITEM_FIELDS:
        hits, tot = _field_accuracy(frame, field)
        pct = hits / tot if tot else 0.0
        print(f"  {field:<24} {hits:>4}/{tot:<5} {pct:>7.1%}")


def main() -> None:
    from app.console import enable_utf8_output

    enable_utf8_output()

    parser = argparse.ArgumentParser(description="Score extraction against the golden set")
    parser.add_argument("--tag", help="Only run cases carrying this tag (spec, regression, adversarial, mixed).")
    parser.add_argument("--id", dest="case_id", help="Only run this one case id.")
    args = parser.parse_args()

    cases = load_cases(tag=args.tag, case_id=args.case_id)
    if not cases:
        print("No cases matched. Check --tag / --id.")
        return

    rows = []
    for case in cases:
        result, meta = run(case["input"])
        actual = result.model_dump()
        scores = score_case(case["expected"], actual)
        rows.append(
            {
                "id": case["id"],
                "tags": ",".join(case.get("tags", [])),
                "input": case["input"],
                "expected": json.dumps(case["expected"], ensure_ascii=False),
                "actual": json.dumps(actual, ensure_ascii=False),
                "note": case.get("note", ""),
                "latency_ms": meta.latency_ms,
                "status": meta.status,
                "needs_review": meta.needs_review,
                **scores,
            }
        )
        mark = "PASS" if scores["exact_match"] else "DIFF"
        print(
            f"[{mark}] {case['id']:<32} items {scores['actual_items']}/{scores['expected_items']}"
            f"  {meta.latency_ms:>6}ms"
        )

    df = pd.DataFrame(rows)

    print()
    print("=" * 62)
    _print_block("OVERALL", df)
    for tag in ("spec", "regression", "adversarial"):
        _print_block(tag.upper(), df[df["tags"].str.contains(tag)])
    print()
    print("=" * 62)
    print(f"Mean latency: {df['latency_ms'].mean():.0f} ms")

    failures = df[~df["exact_match"]]
    if not failures.empty:
        print()
        print("Cases needing a look:")
        for _, row in failures.iterrows():
            print(f"  {row['id']}")
            print(f"    expected: {row['expected']}")
            print(f"    actual  : {row['actual']}")

    out_path = results_path(tag=args.tag, case_id=args.case_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Cases", index=False)

    print()
    print("Where to see these results:")
    print(f"  1. The table above           (per-case PASS/DIFF, per-tag scores, and every miss)")
    print(f"  2. {out_path}")
    print(f"     -> sheet 'Cases': expected vs actual side by side, one row per case")
    print(f"  3. logs/runs.jsonl           (eval calls go through the real pipeline, so they are logged too)")
    print(f"     -> python -m app.log_export  to see them in Excel")


if __name__ == "__main__":
    main()
