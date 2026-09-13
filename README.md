# WhatsApp Order Extraction Service

Turns unstructured WhatsApp order messages — English, Mandarin, or a mix — into validated structured JSON.

```
"Pls send me 10 bags Milo 2kg pack to Penang tomorrow."
                        ↓
{ "items": [ { "product_name": "Milo", "quantity": 10,
               "unit": "bags", "packing_size": "2kg" } ],
  "delivery_location": "Penang",
  "delivery_date": "tomorrow" }
```

FastAPI, two endpoints, one LLM call per message. Tested on a 25-case evaluation set.

This project is built 100 percent by harnessing AI agents. supporting documents to make sure the agents work and remember the progress such as (AGENTS.MD, STATUS.MD, ARCHITECTURE.MD, etc) is not included, feel free to ask the developers how they coworking with AI agents. The reasons of building this type of architecture can be found under ##Assumptions

---

# 1. Architecture — how this is solved

One linear pipeline. A single-skill agent, not multi-skilled agent orchestration: no state machine, no retry loop.

```
   WhatsApp message
          │
          ▼
   ┌─────────────┐
   │ preprocess  │  normalise unicode, collapse spaces, KEEP newlines
   └─────────────┘
          │
          ▼
   ┌─────────────┐
   │   prompt    │  system rules + the 7 worked examples from the brief
   └─────────────┘
          │
          ▼
   ┌─────────────┐
   │     LLM     │  one call to SUMOPOD, structured output
   └─────────────┘
          │
          ▼
   ┌─────────────┐
   │  validate   │  Pydantic parses the response into the schema
   └─────────────┘         └── fails? → empty result + status, never a half-order
          │
          ▼
   ┌─────────────┐
   │ postprocess │  deterministic repairs, flag suspicious results
   └─────────────┘
          │
          ▼
   ┌─────────────┐
   │     log     │  append one line to logs/runs.jsonl
   └─────────────┘
          │
          ▼
    structured JSON
```

The input is unbounded natural language across two languages, so it goes to one LLM call rather than a rules engine. The seven worked examples from the brief go into the prompt few shots, which is where accuracy is tuned. Pydantic is the contract rather than decoration: the model is asked for structured output against the schema, and anything failing validation returns an empty result with a status, so a malformed response can never propagate as a half-filled order. Repairs that can be made in code are made in code, leaving the prompt for judgement. Preprocessing cleans the text but never flattens newlines, because in a list-form order the newline is the item delimiter. Accuracy is measured against 25 tagged golden cases.

---

# 2. The codebase

Each stage is one file with one job, and each runs standalone so a bad answer can be bisected instead of guessed at.

| File | Job |
|---|---|
| `main.py` | Composition root — wires everything, holds no logic |
| `app/config.py` | `.env` settings, paths resolved from the project root |
| `app/console.py` | Makes terminal output UTF-8, so the debug commands can print Mandarin on Windows |
| `app/preprocess.py` | Normalise unicode, collapse spaces, **keep newlines** |
| `app/prompt.py` | System rules + the 7 worked examples ← **accuracy lives here** |
| `app/extractor.py` | The single LLM call — the only file touching the network |
| `app/schemas.py` | Pydantic models — the output contract |
| `app/postprocess.py` | Deterministic repairs, flags suspicious results |
| `app/run_logger.py` | Appends one JSONL line |
| `app/pipeline.py` | Runs the stages in order |
| `app/api.py` | The two routes: `POST /extract`, `GET /health` |
| `app/log_export.py` | JSONL → two-sheet Excel |
| `eval/` | 25 tagged cases + accuracy scoring |
| `tests/` | 115 tests, fully offline |

Debug any stage on its own:

```bash
python -m app.preprocess "我要订购5箱苹果"
python -m app.extractor "Boneless chicken 10kg"
python -m app.pipeline "3 cartons of Coke (1kg)"
```

---

# 3. How to run

Python 3.10+. Developed on 3.13, Windows.

You also may check the demo video here, considering to run this project you have to utilize third party LLM Provider: https://drive.google.com/file/d/1EgFqRWLIUKD8DzsxMAo7424bCFSpuDJy/view?usp=sharing

### Setup

```bash
python -m venv .venv
.venv\Scripts\activate                # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

python -m pytest tests/ -q            # 115 passed — no API key needed

copy .env.example .env                # then set SUMOPOD_API_KEY and SUMOPOD_MODEL
python main.py                        # → http://127.0.0.1:8000/docs
```

### Demo

**Step 1 — open the docs.** Go to `http://127.0.0.1:8000/docs`, expand `POST /extract`, click **Try it out**. The body is pre-filled with a real order — press **Execute**.

**Step 2 — try the three shapes that matter.** Paste each into the same box:

```json
{ "message": "Hi, I want to order 20 kg of Jasmine rice to be delivered to Jalan Ampang this Friday." }
```
```json
{ "message": "我要订购5箱苹果，下星期一送去吉隆坡。" }
```
```json
{ "message": "Fish fillet-5ctn\nPrawn meat -1ctn\nKing prawn-\nCwp bill on next month" }
```

The third is a list-form order: one item per line. **Newlines must be written as `\n`** — pasting real line breaks gives a `422` from the JSON parser before the request reaches the service.

Note what it returns: `King prawn` comes back with `quantity: 0`, not `null`, and the `Cwp bill` line is correctly left out — it is a note, not an order line.

**Step 3 — show the failure modes.** Send `{ "message": "   " }` → `422 message must not be empty`. If the model is unreachable the service returns `503`, never `{"items": []}` — "the service is down" and "this message had no order in it" must not look the same to a caller.

> To demo the `503`, put a wrong `SUMOPOD_BASE_URL` in `.env`. Do **not** demo it by turning off wifi: with no network the client cannot even resolve the host, so it waits out the full timeout twice and looks like a hang.

**Step 4 — show the log.** Every request appended a line to `logs/runs.jsonl`. Press `Ctrl+C` to stop the server — it writes `logs/runs.xlsx` on the way out. Open it: one sheet per run, one sheet per item, with latency, token counts and a `needs_review` flag.

**Step 5 — show the accuracy number.**

```bash
python -m eval.run_eval --tag spec    # 7 calls, ~30s, the examples from the brief
python -m eval.run_eval               # all 25 cases, ~90s
```

Prints a per-field table and writes `eval/results.xlsx` with expected vs actual side by side.

**No server needed** for a single message:

```bash
python main.py --text "3 cartons of Coke (1kg)"
```

---

# 4. Assumptions, limitations, and what comes next

### Assumptions

1. **Single-Skill Agent:** This is a single-skill extraction agent, not multi-skilled agent orchestration with multiple tools and skills. Therefore, identity and extraction rules are defined directly in the system prompt.

2. **Few-Shot Schema Learning:** We use few-shot examples to teach the model the expected extraction behavior and JSON structure. Pydantic is used for response validation, not as an Instructor-style schema sent to the LLM.

3. **Simple Linear Pipeline:** LangGraph is not utilized because this is a stateless extraction task that does not require state management or agent orchestration. LangChain is used only as a thin client for the single model call and its structured output; no chains or tools are needed, because there is nothing to chain together.

4. **Model-Agnostic & Cost-Efficient:** The architecture supports different models capable of English and Mandarin extraction. The current estimate uses DeepSeek V4 Flash. Measured over 76 real requests, usage averages about 1,900 tokens per request (1,423 input, 436 output). At 27,000 requests a month (300 customers ordering 3 times a day), that is roughly 50M tokens. At DeepSeek's official rates ($0.15–$0.30 per 1M input tokens, $0.60–$1.20 per 1M output tokens, off-peak to peak), the cost is about $13–26/month, before any SUMOPOD markup and before savings from caching the repeated prompt. That makes token cost insignificant relative to a $1,500/month subscription.

### If I Got to Collaborate (Limitations and Improvements)

1. **Date Resolution:** Currently, dates are returned as strings. I would improve the system to resolve relative dates into exact dates by passing the current date to the LLM, refining the system prompt, and adding evaluation cases.

2. **Quantity Validation:** Improve postprocessing so quantities reliably reflect the order. Items without a specified quantity still come back with `quantity: 0`, as the brief requires, but would be marked unconfirmed so they are not processed as valid orders until checked.

3. **ERP Product Matching:** The current system extracts customer orders but requires manual matching with ERP products. I would introduce AI skills to retrieve ERP items and use hybrid matching. I would utilize lexical search and semantic similarity with embeddings to identify the most relevant product before sending it to the ERP system.

4. **Order Verification & Feedback:** Add a user verification step before order submission. Verification feedback can be used to improve matching accuracy and evaluate the overall quality of the system over time.
