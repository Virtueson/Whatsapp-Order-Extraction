import pytest

from app.schemas import ExtractionResult, OrderItem


@pytest.fixture
def wired(monkeypatch):
    """Pipeline with the LLM and the logger replaced. No key, no network, no file writes.

    Returns a dict that records what each stage was handed, so the tests can
    assert on the wiring rather than on the model's output.
    """
    import app.pipeline as module

    seen = {"extract_input": None, "logged": None}

    class FakeSettings:
        max_input_chars = 4000

    def fake_extract(text):
        seen["extract_input"] = text
        # Deliberately dirty output: postprocess must clean it up.
        result = ExtractionResult(
            items=[
                OrderItem(product_name="  Coke  ", quantity=-2, unit="  "),
                OrderItem(product_name="   ", quantity=5),
            ],
            delivery_location="  Penang  ",
            delivery_date="",
        )
        meta = {
            "model": "fake-model",
            "latency_ms": 11,
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "status": "ok",
            "error": None,
        }
        return result, meta

    def fake_log_run(record):
        seen["logged"] = record

    monkeypatch.setattr(module, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(module, "extract", fake_extract)
    monkeypatch.setattr(module, "log_run", fake_log_run)
    return module, seen


def test_extractor_receives_preprocessed_text_not_raw(wired):
    """The whole point of the pipeline is that stages run in order."""
    module, seen = wired
    module.run("  20   kg  of   rice  ")
    assert seen["extract_input"] == "20 kg of rice"


def test_newlines_reach_the_extractor_intact(wired):
    module, seen = wired
    module.run("Fish fillet-5ctn\n\nPrawn meat -1ctn")
    assert seen["extract_input"] == "Fish fillet-5ctn\nPrawn meat -1ctn"


def test_postprocessing_is_applied_to_the_result(wired):
    module, _ = wired
    result, _meta = module.run("anything")
    assert len(result.items) == 1               # the unnamed item was dropped
    assert result.items[0].product_name == "Coke"
    assert result.items[0].quantity == 0        # -2 was repaired
    assert result.items[0].unit is None         # "  " became null
    assert result.delivery_location == "Penang"
    assert result.delivery_date is None


def test_meta_carries_script_and_review_flag(wired):
    module, _ = wired
    _result, meta = module.run("我要订购5箱苹果")
    assert meta.script == "cjk"
    assert meta.needs_review is True            # quantity 0 after repair
    assert meta.model == "fake-model"
    assert meta.latency_ms == 11
    assert len(meta.request_id) == 12


def test_log_record_keeps_both_raw_and_preprocessed_input(wired):
    """Storing both is how preprocessing bugs get caught after the fact."""
    module, seen = wired
    module.run("  20   kg  of   rice  ")
    record = seen["logged"]
    assert record["raw_input"] == "  20   kg  of   rice  "
    assert record["preprocessed_input"] == "20 kg of rice"
    assert record["item_count"] == 1
    assert record["needs_review"] is True
    assert record["status"] == "ok"
