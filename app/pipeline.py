"""Runs the extraction stages in order.

This is the ONLY file that knows the pipeline sequence. api.py calls
run() and knows nothing about the stages.

Debug:  python -m app.pipeline "我要订购5箱苹果，下星期一送去吉隆坡。"
"""

import json
import sys
import uuid

from app.config import get_settings
from app.extractor import extract
from app.postprocess import postprocess
from app.preprocess import detect_script, preprocess
from app.run_logger import log_run
from app.schemas import ExtractionMeta, ExtractionResult


def run(raw_text: str) -> tuple[ExtractionResult, ExtractionMeta]:
    """Full pipeline: preprocess -> extract -> postprocess -> log."""
    settings = get_settings()
    request_id = uuid.uuid4().hex[:12]

    cleaned = preprocess(raw_text, max_chars=settings.max_input_chars)
    script = detect_script(cleaned)

    raw_result, llm_meta = extract(cleaned)
    result, needs_review = postprocess(raw_result)

    meta = ExtractionMeta(
        request_id=request_id,
        preprocessed_text=cleaned,
        model=llm_meta["model"],
        latency_ms=llm_meta["latency_ms"],
        script=script,
        needs_review=needs_review,
        status=llm_meta["status"],
        error=llm_meta["error"],
        prompt_tokens=llm_meta["prompt_tokens"],
        completion_tokens=llm_meta["completion_tokens"],
    )

    log_run(
        {
            "request_id": request_id,
            "raw_input": raw_text,
            "preprocessed_input": cleaned,
            "char_count": len(cleaned),
            "script": script,
            "item_count": len(result.items),
            "items": [i.model_dump() for i in result.items],
            "delivery_location": result.delivery_location,
            "delivery_date": result.delivery_date,
            "model": meta.model,
            "latency_ms": meta.latency_ms,
            "prompt_tokens": meta.prompt_tokens,
            "completion_tokens": meta.completion_tokens,
            "status": meta.status,
            "error": meta.error,
            "needs_review": needs_review,
        }
    )

    return result, meta


if __name__ == "__main__":
    from app.console import enable_utf8_output

    enable_utf8_output()
    message = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    result, meta = run(message)
    print("--- RESULT ---")
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
    print("--- META ---")
    print(json.dumps(meta.model_dump(), ensure_ascii=False, indent=2))
