import json

from app.schemas import ExtractionResult, OrderItem


def test_whole_quantity_serializes_as_int_not_float():
    item = OrderItem(product_name="Jasmine rice", quantity=20, unit="kg")
    assert item.model_dump()["quantity"] == 20
    assert json.loads(item.model_dump_json())["quantity"] == 20
    assert "20.0" not in item.model_dump_json()


def test_fractional_quantity_is_preserved():
    item = OrderItem(product_name="Beef", quantity=2.5, unit="kg")
    assert item.model_dump()["quantity"] == 2.5


def test_quantity_defaults_to_zero_not_none():
    item = OrderItem(product_name="King prawn")
    assert item.quantity == 0
    assert item.unit is None
    assert item.packing_size is None


def test_empty_result_is_valid():
    result = ExtractionResult()
    assert result.items == []
    assert result.delivery_location is None
    assert result.delivery_date is None


def test_response_has_exactly_the_three_spec_keys():
    result = ExtractionResult(items=[OrderItem(product_name="Coke", quantity=3)])
    assert set(result.model_dump().keys()) == {
        "items",
        "delivery_location",
        "delivery_date",
    }


def test_item_has_exactly_the_four_spec_keys():
    item = OrderItem(product_name="Coke", quantity=3)
    assert set(item.model_dump().keys()) == {
        "product_name",
        "quantity",
        "unit",
        "packing_size",
    }


def test_mandarin_survives_json_round_trip():
    result = ExtractionResult(
        items=[OrderItem(product_name="苹果", quantity=5, unit="箱")],
        delivery_location="吉隆坡",
        delivery_date="下星期一",
    )
    payload = json.loads(result.model_dump_json())
    assert payload["items"][0]["product_name"] == "苹果"
    assert payload["delivery_location"] == "吉隆坡"
