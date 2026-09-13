from app.postprocess import postprocess
from app.schemas import ExtractionResult, OrderItem


def test_negative_quantity_becomes_zero():
    result, _ = postprocess(
        ExtractionResult(items=[OrderItem(product_name="Coke", quantity=-3)])
    )
    assert result.items[0].quantity == 0


def test_strings_are_stripped():
    result, _ = postprocess(
        ExtractionResult(
            items=[OrderItem(product_name="  Coke  ", quantity=3, unit=" ctn ")],
            delivery_location="  Penang  ",
            delivery_date="  tomorrow  ",
        )
    )
    assert result.items[0].product_name == "Coke"
    assert result.items[0].unit == "ctn"
    assert result.delivery_location == "Penang"
    assert result.delivery_date == "tomorrow"


def test_empty_optional_strings_become_none():
    result, _ = postprocess(
        ExtractionResult(
            items=[OrderItem(product_name="Coke", quantity=3, unit="   ", packing_size="")],
            delivery_location="",
            delivery_date="   ",
        )
    )
    assert result.items[0].unit is None
    assert result.items[0].packing_size is None
    assert result.delivery_location is None
    assert result.delivery_date is None


def test_item_with_blank_product_name_is_dropped():
    result, _ = postprocess(
        ExtractionResult(
            items=[
                OrderItem(product_name="Coke", quantity=3),
                OrderItem(product_name="   ", quantity=5),
            ]
        )
    )
    assert len(result.items) == 1
    assert result.items[0].product_name == "Coke"


def test_duplicate_items_are_kept():
    result, _ = postprocess(
        ExtractionResult(
            items=[
                OrderItem(product_name="Coke", quantity=3, unit="ctn"),
                OrderItem(product_name="Coke", quantity=3, unit="ctn"),
            ]
        )
    )
    assert len(result.items) == 2


def test_needs_review_when_no_items():
    _, needs_review = postprocess(ExtractionResult())
    assert needs_review is True


def test_needs_review_when_a_quantity_is_zero():
    _, needs_review = postprocess(
        ExtractionResult(items=[OrderItem(product_name="King prawn", quantity=0)])
    )
    assert needs_review is True


def test_no_review_needed_for_a_clean_result():
    _, needs_review = postprocess(
        ExtractionResult(
            items=[OrderItem(product_name="Coke", quantity=3, unit="ctn")],
            delivery_location="Penang",
        )
    )
    assert needs_review is False


def test_postprocess_does_not_mutate_the_input():
    original = ExtractionResult(items=[OrderItem(product_name="  Coke  ", quantity=3)])
    postprocess(original)
    assert original.items[0].product_name == "  Coke  "
