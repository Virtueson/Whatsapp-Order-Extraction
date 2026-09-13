"""Deterministic repair of the model's output. Pure function, no LLM.

Pydantic guarantees the SHAPE is right. It does not guarantee the CONTENT
is sane. An LLM can return quantity -3, unit "  ", or an item with no name.
Those are cheap to fix here and expensive to fix in a prompt.

Debug:  python -m app.postprocess "{\"items\": [{\"product_name\": \" Coke \", \"quantity\": -1}]}"
"""

import json
import sys

from app.schemas import ExtractionResult, OrderItem


def _clean_optional(value: str | None) -> str | None:
    """Strip a string; turn blank into None."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def postprocess(result: ExtractionResult) -> tuple[ExtractionResult, bool]:
    """Return (cleaned_result, needs_review). Does not mutate the input."""
    cleaned_items: list[OrderItem] = []

    for item in result.items:
        name = item.product_name.strip() if item.product_name else ""
        if not name:
            # An item with no name is not usable downstream.
            continue

        quantity = item.quantity
        if quantity is None or quantity < 0:
            quantity = 0

        cleaned_items.append(
            OrderItem(
                product_name=name,
                quantity=quantity,
                unit=_clean_optional(item.unit),
                packing_size=_clean_optional(item.packing_size),
            )
        )

    cleaned = ExtractionResult(
        items=cleaned_items,
        delivery_location=_clean_optional(result.delivery_location),
        delivery_date=_clean_optional(result.delivery_date),
    )

    needs_review = (not cleaned.items) or any(i.quantity == 0 for i in cleaned.items)

    return cleaned, needs_review


if __name__ == "__main__":
    from app.console import enable_utf8_output

    enable_utf8_output()
    payload = json.loads(sys.argv[1])
    out, review = postprocess(ExtractionResult(**payload))
    print(json.dumps(out.model_dump(), ensure_ascii=False, indent=2))
    print("needs_review:", review)
