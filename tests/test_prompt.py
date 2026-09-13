import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.prompt import FEW_SHOT, SYSTEM_PROMPT, build_messages


def test_prompt_mentions_json():
    """json_mode is rejected by the provider unless the prompt says 'json'.

    This test exists because removing the word is a silent, runtime-only
    failure: everything imports fine and every offline test still passes.
    """
    assert "json" in SYSTEM_PROMPT.lower()


def test_all_seven_spec_examples_are_present():
    assert len(FEW_SHOT) == 7


def test_message_sequence_is_system_then_pairs_then_user():
    messages = build_messages("my message")
    # 1 system + 7 (human, ai) pairs + 1 final human
    assert len(messages) == 1 + 2 * len(FEW_SHOT) + 1
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[-1], HumanMessage)
    assert messages[-1].content == "my message"
    for i in range(len(FEW_SHOT)):
        assert isinstance(messages[1 + 2 * i], HumanMessage)
        assert isinstance(messages[2 + 2 * i], AIMessage)


def test_few_shot_answers_are_valid_json_with_the_contract_keys():
    for message in build_messages("x"):
        if isinstance(message, AIMessage):
            payload = json.loads(message.content)
            assert set(payload.keys()) == {
                "items",
                "delivery_location",
                "delivery_date",
            }
            for item in payload["items"]:
                assert set(item.keys()) == {
                    "product_name",
                    "quantity",
                    "unit",
                    "packing_size",
                }


def test_mandarin_example_is_not_ascii_escaped():
    """ensure_ascii=False keeps the example readable to the model and to us."""
    mandarin_answers = [
        m.content
        for m in build_messages("x")
        if isinstance(m, AIMessage) and "苹果" in m.content
    ]
    assert len(mandarin_answers) == 1
    assert "\\u" not in mandarin_answers[0]


def test_missing_quantity_example_uses_zero_not_null():
    """Spec example 6: 'King prawn-' must teach quantity 0, never null."""
    king_prawn = [
        item
        for example in FEW_SHOT
        for item in example["output"]["items"]
        if item["product_name"] == "King prawn"
    ]
    assert len(king_prawn) == 1
    assert king_prawn[0]["quantity"] == 0
    assert king_prawn[0]["unit"] is None


def test_non_order_line_is_not_taught_as_an_item_or_a_date():
    """'Cwp bill on next month' must be dropped entirely, not parsed."""
    for example in FEW_SHOT:
        if "Cwp bill" in example["input"]:
            assert example["output"]["delivery_date"] is None
            names = [i["product_name"] for i in example["output"]["items"]]
            assert not any("Cwp" in n or "bill" in n.lower() for n in names)
            break
    else:
        raise AssertionError("the Cwp bill example is missing from FEW_SHOT")
