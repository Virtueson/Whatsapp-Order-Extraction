"""Offline tests for the eval scoring logic.

The eval SCRIPT costs money and needs an API key, so it is not a test. Its
scoring functions are pure, and a wrong scorer is worse than no scorer -
it would report a number nobody should trust.
"""

import json

from app.config import PROJECT_ROOT
from eval.run_eval import load_cases, results_path, same, score_case


def _result(items=None, location=None, date=None) -> dict:
    return {
        "items": items or [],
        "delivery_location": location,
        "delivery_date": date,
    }


def _item(name, qty=0, unit=None, packing=None) -> dict:
    return {
        "product_name": name,
        "quantity": qty,
        "unit": unit,
        "packing_size": packing,
    }


# --- same() ---

def test_none_equals_none():
    assert same(None, None) is True


def test_none_never_equals_a_value():
    assert same(None, "Penang") is False
    assert same("Penang", None) is False


def test_numbers_compare_numerically():
    assert same(20, 20.0) is True
    assert same(0.5, 0.5) is True
    assert same(20, 21) is False


def test_strings_compare_case_insensitively_and_trimmed():
    assert same("Penang", " penang ") is True
    assert same("Milo", "Nescafe") is False


def test_zero_is_not_treated_as_missing():
    """quantity 0 means 'not specified' and must not collapse into None."""
    assert same(0, None) is False
    assert same(0, 0) is True


# --- score_case() ---

def test_identical_results_score_a_perfect_match():
    expected = _result([_item("Milo", 10, "bags", "2kg")], "Penang", "tomorrow")
    scores = score_case(expected, dict(expected))
    assert scores["exact_match"] is True
    assert scores["item_count_match"] is True
    assert scores["product_name_hits"] == 1
    assert scores["delivery_location"] is True


def test_one_wrong_field_breaks_exact_match_but_not_the_others():
    expected = _result([_item("Milo", 10, "bags", "2kg")], "Penang", "tomorrow")
    actual = _result([_item("Milo", 10, "bags", None)], "Penang", "tomorrow")

    scores = score_case(expected, actual)
    assert scores["exact_match"] is False
    assert scores["packing_size_hits"] == 0
    assert scores["product_name_hits"] == 1
    assert scores["quantity_hits"] == 1
    assert scores["delivery_location"] is True


def test_a_missing_item_costs_count_match_not_every_field():
    """A dropped item must not drag down the fields of the items we did get."""
    expected = _result([_item("Milo", 10, "bags"), _item("eggs", 5, "boxes")])
    actual = _result([_item("Milo", 10, "bags")])

    scores = score_case(expected, actual)
    assert scores["item_count_match"] is False
    assert scores["exact_match"] is False
    assert scores["expected_items"] == 2
    assert scores["actual_items"] == 1
    # Only the one overlapping position is scored.
    assert scores["product_name_total"] == 1
    assert scores["product_name_hits"] == 1


def test_empty_expected_and_empty_actual_is_an_exact_match():
    """A message with no order is a correct answer, not a hole in the data."""
    scores = score_case(_result(), _result())
    assert scores["exact_match"] is True
    assert scores["item_count_match"] is True


def test_hallucinated_item_against_an_empty_expected_fails():
    scores = score_case(_result(), _result([_item("Milo", 1)]))
    assert scores["exact_match"] is False
    assert scores["item_count_match"] is False


def test_quantity_zero_versus_null_is_scored_as_wrong():
    expected = _result([_item("King prawn", 0, None)])
    actual = _result([_item("King prawn", None, None)])
    assert score_case(expected, actual)["quantity_hits"] == 0


# --- the golden set itself ---

def test_golden_set_parses_and_has_unique_ids():
    cases = load_cases()
    assert len(cases) >= 20
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))


def test_every_golden_case_matches_the_output_contract():
    for case in load_cases():
        expected = case["expected"]
        assert set(expected) == {"items", "delivery_location", "delivery_date"}, case["id"]
        for item in expected["items"]:
            assert set(item) == {
                "product_name",
                "quantity",
                "unit",
                "packing_size",
            }, case["id"]


def test_all_seven_spec_cases_are_present():
    assert len(load_cases(tag="spec")) == 7


def test_tag_and_id_filters_work():
    assert all("adversarial" in c["tags"] for c in load_cases(tag="adversarial"))
    single = load_cases(case_id="spec-6-list-form")
    assert len(single) == 1
    assert single[0]["expected"]["items"][2]["quantity"] == 0


def test_golden_file_is_readable_utf8_not_escaped():
    raw = (PROJECT_ROOT / "eval" / "golden.jsonl").read_bytes()
    assert "苹果".encode("utf-8") in raw
    assert b"\\u82f9" not in raw


def test_spec_one_records_its_intended_divergence():
    """We return "this Friday" where the brief says "Friday". That is a
    deliberate choice, so the golden file must carry the brief's value too."""
    case = load_cases(case_id="spec-1-english")[0]
    assert case["expected"]["delivery_date"] == "this Friday"
    assert case["spec_expected_delivery_date"] == "Friday"
    assert "DIVERGENCE" in case["note"]


def test_golden_file_is_one_object_per_line():
    """JSONL: an embedded newline would silently split a case in two."""
    path = PROJECT_ROOT / "eval" / "golden.jsonl"
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            json.loads(line)  # raises with the line number in the traceback if broken
            assert line.startswith("{") and line.rstrip().endswith("}"), number


# --- results file naming ---

def test_full_run_writes_the_canonical_results_file():
    assert results_path().name == "results.xlsx"


def test_a_filtered_run_never_overwrites_the_full_report():
    """`--tag spec` writing 7 rows over a 25-case report would destroy the
    number being quoted in the write-up."""
    assert results_path(tag="spec").name == "results-spec.xlsx"
    assert results_path(tag="adversarial").name == "results-adversarial.xlsx"
    assert results_path(tag="spec") != results_path()


def test_a_single_case_run_gets_its_own_file():
    assert results_path(case_id="spec-6-list-form").name == "results-spec-6-list-form.xlsx"


def test_id_filter_wins_over_tag_for_naming():
    assert results_path(tag="spec", case_id="spec-1-english").name == "results-spec-1-english.xlsx"
