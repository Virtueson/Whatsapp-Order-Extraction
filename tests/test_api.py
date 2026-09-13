import ast
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.schemas import ExtractionMeta, ExtractionResult, OrderItem


class _FakeSettings:
    """Stands in for real settings so tests never need a .env or an API key."""

    sumopod_api_key = "test-key-1234567890"
    sumopod_model = "fake-model"
    sumopod_base_url = "https://api.sumopod.com/v1"


def _ok_run(raw_text: str):
    result = ExtractionResult(
        items=[OrderItem(product_name="Milo", quantity=10, unit="bags", packing_size="2kg")],
        delivery_location="Penang",
        delivery_date="tomorrow",
    )
    meta = ExtractionMeta(
        request_id="test123",
        preprocessed_text=raw_text.strip(),
        model="fake-model",
        latency_ms=42,
        script="latin",
        needs_review=False,
    )
    return result, meta


def _mandarin_run(raw_text: str):
    result = ExtractionResult(
        items=[OrderItem(product_name="苹果", quantity=5, unit="箱")],
        delivery_location="吉隆坡",
        delivery_date="下星期一",
    )
    meta = ExtractionMeta(
        request_id="test789",
        preprocessed_text=raw_text.strip(),
        model="fake-model",
        latency_ms=50,
        script="cjk",
        needs_review=False,
    )
    return result, meta


def _failing_run(raw_text: str):
    """Simulates SUMOPOD being unreachable."""
    meta = ExtractionMeta(
        request_id="test456",
        preprocessed_text=raw_text.strip(),
        model="fake-model",
        latency_ms=30000,
        script="latin",
        needs_review=True,
        status="llm_error",
        error="APITimeoutError: request timed out",
    )
    return ExtractionResult(), meta


@pytest.fixture
def api_module(monkeypatch):
    """The api module with settings stubbed out - no .env required."""
    import app.api as mod

    monkeypatch.setattr(mod, "get_settings", lambda: _FakeSettings())
    return mod


def _client_running(api_module, monkeypatch, fake_run):
    monkeypatch.setattr(api_module, "run", fake_run)
    return TestClient(api_module.create_app())


@pytest.fixture
def client(api_module, monkeypatch):
    """A test client whose pipeline is mocked - no API key, no network."""
    return _client_running(api_module, monkeypatch, _ok_run)


@pytest.fixture
def mandarin_client(api_module, monkeypatch):
    return _client_running(api_module, monkeypatch, _mandarin_run)


@pytest.fixture
def failing_client(api_module, monkeypatch):
    """A test client whose pipeline always reports an LLM failure."""
    return _client_running(api_module, monkeypatch, _failing_run)


# --- The response contract ---

def test_extract_returns_exactly_the_three_spec_keys(client):
    response = client.post("/extract", json={"message": "10 bags Milo 2kg to Penang tomorrow"})
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"items", "delivery_location", "delivery_date"}


def test_extract_item_shape_matches_the_spec(client):
    body = client.post("/extract", json={"message": "anything"}).json()
    assert set(body["items"][0].keys()) == {
        "product_name",
        "quantity",
        "unit",
        "packing_size",
    }
    assert body["items"][0]["quantity"] == 10


def test_the_response_never_carries_diagnostics(client):
    """There is no way to make the endpoint return `_meta`. The old ?debug=1
    flag was removed as redundant: the same diagnostics, and more, are written
    to logs/runs.jsonl on every single run.

    The query string is passed here to prove the flag is genuinely gone rather
    than merely undocumented - FastAPI ignores unknown query parameters, so
    this must still come back as the plain three-key response.
    """
    for url in ("/extract", "/extract?debug=1"):
        body = client.post(url, json={"message": "anything"}).json()
        assert "_meta" not in body
        assert set(body) == {"items", "delivery_location", "delivery_date"}


def test_mandarin_is_returned_readable_not_escaped(mandarin_client):
    """Starlette must not ascii-escape the response body."""
    response = mandarin_client.post("/extract", json={"message": "我要订购5箱苹果"})
    assert "苹果".encode("utf-8") in response.content
    assert b"\\u82f9" not in response.content
    assert response.json()["delivery_location"] == "吉隆坡"


# --- Input validation ---

def test_empty_message_is_rejected(client):
    response = client.post("/extract", json={"message": "   "})
    assert response.status_code == 422


def test_missing_message_field_is_rejected(client):
    response = client.post("/extract", json={})
    assert response.status_code == 422


# --- Failure handling ---

def test_llm_failure_returns_503_not_a_silent_empty_result(failing_client):
    """An unreachable model must not look like 'this message had no order in it'."""
    response = failing_client.post("/extract", json={"message": "3 cartons of Coke"})
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()


def test_health_reports_configured_without_leaking_the_key(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["api_key_configured"] is True
    # The key VALUE must never appear anywhere in the response.
    assert _FakeSettings.sumopod_api_key not in response.text


# --- the endpoint surface ---

def test_the_service_exposes_exactly_two_endpoints(api_module):
    """Two endpoints, deliberately: /extract does the job, /health reports
    configuration. Operational concerns are wired in by main.py, not exposed
    over HTTP."""
    app = api_module.create_app()
    routes = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
    }
    # FastAPI adds its own docs routes; ours are the rest.
    ours = {
        (m, p)
        for (m, p) in routes
        if not p.startswith("/docs")
        and not p.startswith("/redoc")
        and not p.startswith("/openapi")
    }
    assert ours == {("POST", "/extract"), ("GET", "/health")}


def test_docs_page_hides_the_schemas_block(api_module):
    """The Schemas section at the bottom of /docs lists FastAPI's internal
    validation-error models, which mean nothing to someone reading this API.
    The request shape is still documented inline on POST /extract."""
    app = api_module.create_app()
    assert app.swagger_ui_parameters["defaultModelsExpandDepth"] == -1


def test_docs_show_a_real_response_example_not_the_word_string(api_module):
    """The endpoint returns a raw JSONResponse so the body stays exactly three
    keys, which leaves FastAPI with no response schema to document - it renders
    the 200 case as the word "string". These examples fill that gap, and the
    503 case is documented at all only because we declare it."""
    spec = api_module.create_app().openapi()
    responses = spec["paths"]["/extract"]["post"]["responses"]

    assert set(responses) == {"200", "422", "503"}

    example = responses["200"]["content"]["application/json"]["example"]
    assert set(example) == {"items", "delivery_location", "delivery_date"}
    assert example["items"][0]["product_name"]

    body_example = spec["components"]["schemas"]["ExtractRequest"]["examples"][0]
    assert body_example["message"] != "string"


def test_docs_explain_the_newline_rule_on_the_message_field(api_module):
    """List-form orders are the common WhatsApp shape and the one people send
    wrong: pasting real line breaks into the JSON body fails with
    `json_invalid: Invalid control character` before the request reaches us.

    There is only one request example, so the rule has to live on the `message`
    field description - which is exactly where someone editing the body reads.
    """
    spec = api_module.create_app().openapi()
    field = spec["components"]["schemas"]["ExtractRequest"]["properties"]["message"]

    assert "\\n" in field["description"]
    assert "line" in field["description"].lower()


def test_the_web_layer_does_not_import_the_export_module(api_module):
    """api.py must not import the Excel export. Regenerating the workbook is
    wired in by main.py, the composition root, so the web layer never touches
    the filesystem.

    Parsed rather than grepped, so the docstring explaining this rule does
    not trip the test that enforces it.
    """
    tree = ast.parse(Path(api_module.__file__).read_text(encoding="utf-8"))

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert "app.log_export" not in imported, imported
    assert not any(name.startswith("scripts") for name in imported), imported
