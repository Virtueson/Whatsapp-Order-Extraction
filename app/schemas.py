"""The output contract.

These models are the single source of truth for what "extracted data"
means. The LLM is asked to produce ExtractionResult; everything else in
the pipeline conforms to it.
"""

from pydantic import BaseModel, Field, field_serializer


class OrderItem(BaseModel):
    """One product line from a customer's message."""

    product_name: str = Field(
        description="Product name, verbatim, in its original language."
    )
    quantity: float = Field(
        default=0,
        description="How much is being ordered. 0 means not specified.",
    )
    unit: str | None = Field(
        default=None,
        description="Unit of the quantity, e.g. kg, bags, ctn, boxes.",
    )
    packing_size: str | None = Field(
        default=None,
        description="How the product is packaged, e.g. '2kg', '10kg pack'.",
    )

    @field_serializer("quantity")
    def _serialize_quantity(self, value: float) -> int | float:
        """Emit 20 rather than 20.0, but keep 2.5 as 2.5."""
        return int(value) if float(value).is_integer() else value


class ExtractionResult(BaseModel):
    """The full extraction. This IS the API response shape - no extra keys."""

    items: list[OrderItem] = Field(default_factory=list)
    delivery_location: str | None = None
    delivery_date: str | None = None


class ExtractRequest(BaseModel):
    """Request body for POST /extract."""

    message: str = Field(
        description=(
            "The raw WhatsApp message text. For a multi-item order, put each "
            "item on its own line and write the line breaks as \\n - the "
            "newlines are the item delimiter and are preserved. A real line "
            "break inside a JSON string is invalid JSON and is rejected by the "
            "parser before it reaches this service."
        )
    )

    # Pre-fills "Try it out" in the docs with a real order instead of the word
    # "string", so a reviewer can press Execute and see the service work. One
    # example, deliberately: a dropdown of variants would be teaching the same
    # request shape three times over. The \n rule for multi-item orders is on
    # the field description above, where someone editing the body will read it.
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"message": "Pls send me 10 bags Milo 2kg pack to Penang tomorrow."}
            ]
        }
    }


class ExtractionMeta(BaseModel):
    """Diagnostics for the log. Never returned over HTTP - the response is
    always exactly the three fields the spec asks for."""

    request_id: str
    preprocessed_text: str
    model: str
    latency_ms: int
    script: str | None = None
    needs_review: bool = False
    status: str = "ok"
    error: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
