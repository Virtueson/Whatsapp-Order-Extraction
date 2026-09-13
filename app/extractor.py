"""The single LLM call. The only file in the project that touches the network.

SUMOPOD is OpenAI-compatible, so ChatOpenAI connects to it by setting
base_url. If the configured model rejects structured output via function
calling, see FALLBACK below.

Debug:  python -m app.extractor "Pls send me 10 bags Milo 2kg pack to Penang tomorrow."
"""

import json
import sys
import time
from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.prompt import build_messages
from app.schemas import ExtractionResult


@lru_cache(maxsize=1)
def get_structured_llm():
    """Build the chat model once and reuse it across requests."""
    settings = get_settings()
    llm = ChatOpenAI(
        api_key=settings.sumopod_api_key,
        base_url=settings.sumopod_base_url,
        model=settings.sumopod_model,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
    )
    # How we ask for structured output is configurable because it depends on the
    # model, not on us. deepseek-v4-flash behind SUMOPOD rejects function calling
    # ("Thinking mode does not support this tool_choice"), so json_mode is the
    # default. Models that prefer tool calling can set LLM_STRUCTURED_MODE.
    return llm.with_structured_output(
        ExtractionResult,
        include_raw=True,
        method=settings.llm_structured_mode,
    )


def extract(text: str) -> tuple[ExtractionResult, dict]:
    """Send the message to the LLM and return (result, meta).

    Never raises on a model or network problem. On failure it returns an
    empty-but-valid ExtractionResult and records the reason in meta.
    """
    settings = get_settings()
    meta: dict = {
        "model": settings.sumopod_model,
        "latency_ms": 0,
        "prompt_tokens": None,
        "completion_tokens": None,
        "status": "ok",
        "error": None,
    }

    if not text.strip():
        meta["status"] = "empty_input"
        return ExtractionResult(), meta

    started = time.perf_counter()
    try:
        response = get_structured_llm().invoke(build_messages(text))
    except Exception as exc:
        meta["latency_ms"] = int((time.perf_counter() - started) * 1000)
        meta["status"] = "llm_error"
        meta["error"] = f"{type(exc).__name__}: {exc}"
        return ExtractionResult(), meta

    meta["latency_ms"] = int((time.perf_counter() - started) * 1000)

    raw = response.get("raw")
    usage = getattr(raw, "usage_metadata", None) or {}
    meta["prompt_tokens"] = usage.get("input_tokens")
    meta["completion_tokens"] = usage.get("output_tokens")

    if response.get("parsing_error") is not None:
        meta["status"] = "parse_error"
        meta["error"] = str(response["parsing_error"])
        return ExtractionResult(), meta

    parsed = response.get("parsed")
    if parsed is None:
        meta["status"] = "empty_response"
        meta["error"] = "Model returned no parsable structured output."
        return ExtractionResult(), meta

    return parsed, meta


if __name__ == "__main__":
    from app.console import enable_utf8_output

    enable_utf8_output()
    message = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    result, meta = extract(message)
    print("--- RAW MODEL OUTPUT (before postprocessing) ---")
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
    print("--- META ---")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
