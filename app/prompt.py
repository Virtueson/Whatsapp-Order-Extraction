"""The system prompt and few-shot examples.

THIS FILE IS WHERE EXTRACTION ACCURACY LIVES. To improve results, edit
the rules or add examples here - not the surrounding code.

We build message objects directly rather than using ChatPromptTemplate,
because the templating layer would try to interpret the { } in our JSON
examples as variables.

Debug:  python -m app.prompt
"""

import json

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

# NOTE: the word "json" must appear somewhere in this prompt. Providers reject a
# json-mode request whose prompt never mentions json ("Prompt must contain the word
# 'json' in some form"). tests/test_prompt.py guards this.
SYSTEM_PROMPT = """You extract structured order information from WhatsApp messages sent by customers.

Messages may be in English, Mandarin, or a mix of both. They are informal: typos, shorthand, missing punctuation, and list formats are all normal.

Return the extracted data using the provided schema.

## Fields

- product_name: the product, written exactly as the customer wrote it, in its original language. Remove quantity and unit words from it. Keep the original capitalisation.
- quantity: how much is being ordered, as a number.
- unit: the unit of that quantity, exactly as written (kg, bags, ctn, boxes, and so on).
- packing_size: how the product itself is packaged or specified (e.g. "2kg", "10kg pack", "1mm").
- delivery_location: where it goes, exactly as written.
- delivery_date: when it should arrive, exactly as written.

## Rules

1. QUANTITY vs PACKING_SIZE is the hardest judgment. Apply this rule:
   - If a product has ONE measurement, that is the quantity and unit. packing_size is null.
     "Boneless chicken 10kg" -> quantity 10, unit "kg", packing_size null
   - If a product has TWO measurements, the one saying HOW MUCH IS ORDERED is the
     quantity, and the one DESCRIBING THE PRODUCT is the packing_size.
     "10 bags Milo 2kg pack" -> quantity 10, unit "bags", packing_size "2kg"
     "Beef short plate 1mm 2kg" -> quantity 2, unit "kg", packing_size "1mm"
     "2 kg of Jasmine rice (10kg pack)" -> quantity 2, unit "kg", packing_size "10kg pack"

2. If a product is listed with NO quantity, set quantity to 0. Never null.
   "King prawn-" -> quantity 0, unit null

3. Return delivery_date and delivery_location EXACTLY AS WRITTEN. Do not convert
   them to calendar dates. "this Friday" stays "this Friday". "1 Oct" stays "1 Oct".
   Mandarin dates stay in Mandarin.

4. IGNORE lines that are not product orders: greetings, thanks, payment terms,
   invoicing notes, general chatter. For example "Cwp bill on next month" is a
   payment note. It is NOT a delivery date and NOT a product. Drop it entirely.

5. Each line of a list-form message is usually a separate item.

6. If a field is not mentioned in the message, return null for it.

7. If the message contains no product order at all, return an empty items list.

8. Never invent information. Only extract what is actually in the message.

## Output

Respond with a single json object matching the schema, and nothing else.
"""

# The seven worked examples from the specification. These are the contract.
FEW_SHOT: list[dict] = [
    {
        "input": "Hi, I want to order 20 kg of Jasmine rice to be delivered to Jalan Ampang this Friday.",
        "output": {
            "items": [
                {"product_name": "Jasmine rice", "quantity": 20, "unit": "kg", "packing_size": None}
            ],
            "delivery_location": "Jalan Ampang",
            "delivery_date": "Friday",
        },
    },
    {
        "input": "我要订购5箱苹果，下星期一送去吉隆坡。",
        "output": {
            "items": [
                {"product_name": "苹果", "quantity": 5, "unit": "箱", "packing_size": None}
            ],
            "delivery_location": "吉隆坡",
            "delivery_date": "下星期一",
        },
    },
    {
        "input": "Pls send me 10 bags Milo 2kg pack to Penang tomorrow.",
        "output": {
            "items": [
                {"product_name": "Milo", "quantity": 10, "unit": "bags", "packing_size": "2kg"}
            ],
            "delivery_location": "Penang",
            "delivery_date": "tomorrow",
        },
    },
    {
        "input": "Can I get 3 cartons of Coke (1kg)?",
        "output": {
            "items": [
                {"product_name": "Coke", "quantity": 3, "unit": "cartons", "packing_size": "1kg"}
            ],
            "delivery_location": None,
            "delivery_date": None,
        },
    },
    {
        "input": "I want to order 2 kg of Jasmine rice (10kg pack) and 5 boxes of eggs.",
        "output": {
            "items": [
                {"product_name": "Jasmine rice", "quantity": 2, "unit": "kg", "packing_size": "10kg pack"},
                {"product_name": "eggs", "quantity": 5, "unit": "boxes", "packing_size": None},
            ],
            "delivery_location": None,
            "delivery_date": None,
        },
    },
    {
        "input": "Fish fillet-5ctn\nPrawn meat -1ctn\nKing prawn-\nCwp bill on next month",
        "output": {
            "items": [
                {"product_name": "Fish fillet", "quantity": 5, "unit": "ctn", "packing_size": None},
                {"product_name": "Prawn meat", "quantity": 1, "unit": "ctn", "packing_size": None},
                {"product_name": "King prawn", "quantity": 0, "unit": None, "packing_size": None},
            ],
            "delivery_location": None,
            "delivery_date": None,
        },
    },
    {
        "input": (
            "Boneless chicken 10kg\n"
            "Pork chop bone in 5kg\n"
            "Beef brisket 5kg\n"
            "Beef short plate 1mm 2kg\n"
            "Deliver 1 Oct"
        ),
        "output": {
            "items": [
                {"product_name": "Boneless chicken", "quantity": 10, "unit": "kg", "packing_size": None},
                {"product_name": "Pork chop bone in", "quantity": 5, "unit": "kg", "packing_size": None},
                {"product_name": "Beef brisket", "quantity": 5, "unit": "kg", "packing_size": None},
                {"product_name": "Beef short plate", "quantity": 2, "unit": "kg", "packing_size": "1mm"},
            ],
            "delivery_location": None,
            "delivery_date": "1 Oct",
        },
    },
]


def build_messages(text: str) -> list[BaseMessage]:
    """System prompt + few-shot conversation + the customer's message."""
    messages: list[BaseMessage] = [SystemMessage(content=SYSTEM_PROMPT)]
    for example in FEW_SHOT:
        messages.append(HumanMessage(content=example["input"]))
        messages.append(
            AIMessage(content=json.dumps(example["output"], ensure_ascii=False))
        )
    messages.append(HumanMessage(content=text))
    return messages


if __name__ == "__main__":
    from app.console import enable_utf8_output

    enable_utf8_output()
    for msg in build_messages("<<< THE CUSTOMER MESSAGE GOES HERE >>>"):
        print(f"===== {msg.type.upper()} =====")
        print(msg.content)
        print()
