"""FastAPI routes. No business logic - validate, delegate, shape the response.

Two endpoints, deliberately: /extract does the job, /health says whether the
service is configured. Anything operational - regenerating the Excel report,
for instance - is wired in by main.py, so this module never touches the
filesystem.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.pipeline import run
from app.schemas import ExtractRequest


# What /docs shows under "Responses". Without this FastAPI has nothing to go on
# - the endpoint returns a raw JSONResponse, deliberately, so that the body is
# EXACTLY the three spec'd keys - and it renders the 200 case as the word
# "string", which teaches a reviewer nothing. These examples are the same
# worked example as the exercise brief.
_EXTRACT_RESPONSES = {
    200: {
        "description": "The extracted order. Fields absent from the message come back as null.",
        "content": {
            "application/json": {
                "example": {
                    "items": [
                        {
                            "product_name": "Milo",
                            "quantity": 10,
                            "unit": "bags",
                            "packing_size": "2kg",
                        }
                    ],
                    "delivery_location": "Penang",
                    "delivery_date": "tomorrow",
                }
            }
        },
    },
    422: {
        "description": "The message was empty, or the request body was malformed.",
        "content": {
            "application/json": {"example": {"detail": "message must not be empty"}}
        },
    },
    503: {
        "description": (
            "The language model could not be reached. Deliberately NOT an empty "
            "result: 'the service is down' and 'this message had no order in it' "
            "must not look the same to a caller."
        ),
        "content": {
            "application/json": {
                "example": {
                    "detail": "Extraction service unavailable: the language model could not be reached."
                }
            }
        },
    },
}

_HEALTH_RESPONSES = {
    200: {
        "description": "The service is configured. Note this does NOT call the model.",
        "content": {
            "application/json": {
                "example": {
                    "status": "ok",
                    "api_key_configured": True,
                    "model": "deepseek-v4-flash",
                    "base_url": "https://ai.sumopod.com/v1",
                }
            }
        },
    },
    503: {
        "description": "No .env or no SUMOPOD_API_KEY. Copy .env.example to .env.",
        "content": {
            "application/json": {
                "example": {"status": "misconfigured", "api_key_configured": False}
            }
        },
    },
}


def create_app(lifespan=None) -> FastAPI:
    """Build the app.

    `lifespan` is injected by the composition root rather than defined here.
    That is what keeps the Excel export - which writes to disk - out of the
    web layer. tests/test_api.py enforces that api.py never imports it.
    """
    app = FastAPI(
        title="WhatsApp Order Extraction Service",
        description=(
            "Turns unstructured English/Mandarin WhatsApp order messages into "
            "structured JSON. Every run is logged to logs/runs.jsonl with full "
            "diagnostics; the response itself is only ever the three fields the "
            "spec asks for."
        ),
        version="1.0.0",
        lifespan=lifespan,
        # Hide the "Schemas" block at the bottom of /docs. Two of the three
        # entries there (HTTPValidationError, ValidationError) are FastAPI's
        # own internals, and the third is already shown inline on POST
        # /extract - so the block adds nothing but noise for a reviewer.
        swagger_ui_parameters={"defaultModelsExpandDepth": -1},
    )

    @app.post(
        "/extract",
        summary="Extract a structured order from a WhatsApp message",
        responses=_EXTRACT_RESPONSES,
    )
    def extract_endpoint(payload: ExtractRequest):
        if not payload.message or not payload.message.strip():
            raise HTTPException(status_code=422, detail="message must not be empty")

        result, meta = run(payload.message)

        # A network/timeout failure is NOT the same as "no items in the message".
        # Returning an empty result here would silently lie to the caller.
        if meta.status == "llm_error":
            raise HTTPException(
                status_code=503,
                detail="Extraction service unavailable: the language model could not be reached.",
            )

        # EXACTLY the three spec'd keys. Nothing else, under any circumstances.
        # The diagnostics in `meta` are not discarded - run() has already written
        # them to logs/runs.jsonl, which is where you go to debug a bad answer.
        return JSONResponse(content=result.model_dump())

    @app.get(
        "/health",
        summary="Is the service configured?",
        responses=_HEALTH_RESPONSES,
    )
    def health_endpoint():
        try:
            settings = get_settings()
            return {
                "status": "ok",
                "api_key_configured": bool(settings.sumopod_api_key),
                "model": settings.sumopod_model,
                "base_url": settings.sumopod_base_url,
            }
        except Exception:
            return JSONResponse(
                status_code=503,
                content={"status": "misconfigured", "api_key_configured": False},
            )

    return app
