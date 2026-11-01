# OpenAI Decisions API — reference for T4

Source: https://developers.openai.com/api/docs/guides/decisions (read 2026-11-01).
Copied from the guide for sessions that can't reach `developers.openai.com`. Anything the guide
does not state is marked **not documented**: don't guess it, fixture it from a real response in T9.

## Endpoint

- `POST /v1/decisions`
- Model: `gpt-6-luna` is the only supported model.
- Status: generally available. The guide describes typed answers that come back "about 10x faster than the Responses API".
- Python SDK: `client.decisions.create(...)` (`openai.OpenAI`). Use the async client in agentkit (`openai.AsyncOpenAI`; the async method name isn't shown in the guide, but it should mirror the sync one).

## Request

| Field | Type / notes |
|---|---|
| `model` | `"gpt-6-luna"` (required) |
| `input` | Shared evidence. Either a string, or an ordered array of messages, tool calls and tool outputs |
| `questions` | Array, **1–400** items |
| `prompt_cache_key` | Optional string. Partitions cache reuse by a caller key; agentkit uses the thread id |
| `prompt_cache_breakpoint` | `{"mode": "explicit"}`, set on text or image parts inside `input` |
| `prompt_cache_options.mode` | `"explicit"` makes the API use only the breakpoints you marked |

### `input` contents

- Roles: user, developer/system and assistant messages, plus function and custom tool calls and their outputs. Each tool output links back to its call via `call_id`.
- Parts: text and images. Images are base64 data URLs or public http(s) URLs; `file_id` is **not** supported.
- JSON: an `input_json` part with a `data` field, allowed in `user` messages only.
- Not supported: files, audio, item references.

### Question object

Common fields:
- `type`: `"predicate"`, `"choice"` or `"score"`.
- `name`: unique within the request; the answer echoes it back.
- `instructions`: a string, or an array of `input_text` / `input_image` parts.

Fields for each type:
- `choice` adds `choices: [{ "value": str, "description": str }, ...]`.
- `score` adds `levels: [{ "label": str, "description": str }, ...]` with 2–10 levels, ordered lowest to highest.
- `predicate` adds nothing.

## Response

```json
{
  "answers": [
    { "type": "predicate", "name": "tool:web_search", "probability": 0.92 },
    { "type": "choice", "name": "model_tier", "choice": "standard",
      "probabilities": [{ "value": "standard", "probability": 0.95 }], "confidence": 0.93 },
    { "type": "score", "name": "complexity", "score": 1.1,
      "probabilities": [{ "value": 0, "label": "simple", "probability": 0.1 }], "confidence": 0.55 }
  ],
  "usage": { "input_tokens": 0, "input_tokens_details": { "cached_tokens": 0, "cache_write_tokens": 0 } }
}
```

| Answer type | Fields |
|---|---|
| `predicate` | `probability` in the range 0–1 |
| `choice` | `choice` (one of the supplied values), `probabilities[]` of `{value, probability}`, `confidence` |
| `score` | `score` (probability-weighted mean of the 0-based level indices), `probabilities[]` of `{value, label, probability}`, `confidence` |
| `refusal` | Appears in the SDK examples with `name`. Its other fields are **not documented**; treat it as "no answer" |

The guide doesn't say whether the answers come back in question order. Match them by `name`, never by position.
The `usage` field names come from the guide's caching section; the rest of the `usage` object is **not documented**.

## Prompt caching

- On by default, with an implicit breakpoint at the end of the shared `input`.
- The reusable prefix must be **at least 1,024 tokens**. Question content doesn't count toward that.
- Usage reports cache reads as `usage.input_tokens_details.cached_tokens` and cache writes as `cache_write_tokens`; both are included in `usage.input_tokens`.
- Breakpoints aren't supported inside question `instructions`.

## Pricing and limits

- Uncached input costs **$0.10 per 1M tokens**. Cache reads are discounted and cache writes charged at the standard `gpt-6-luna` caching rates. **Output tokens are free.**
- Regional processing premiums and long-context multipliers may apply.
- Image count and size limits: **not documented**. Rate limits and per-request timeouts: **not documented**.
- Usage endpoint: `GET /v1/organization/usage/decisions`, which needs an admin key with `api.usage.read`. Its `num_model_requests` counts requests, not questions.
- ZDR and HIPAA are available to eligible customers. Regional processing is offered in the US and the EU (EEA + Switzerland). Private Link is supported.

## SDK example (from the guide)

```python
from openai import OpenAI

client = OpenAI()
decision = client.decisions.create(
    model="gpt-6-luna",
    input="I was charged twice for my order.",
    questions=[{
        "type": "choice",
        "name": "department",
        "instructions": "Which department should handle this complaint?",
        "choices": [
            {"value": "billing", "description": "Payments, invoices, and refunds."},
            {"value": "technical", "description": "Problems using the product."},
            {"value": "other", "description": "Requests outside these categories."},
        ],
    }],
)
answer = decision.answers[0]
if answer.type == "choice":
    print(answer.choice, answer.confidence)
```

## How agentkit maps onto it (T4 / T5)

One request per thread, made on the first model call. T5 caches the result per thread.

- `input`: the system prompt, the tool catalog (name and description for each tool) and the conversation so far. Put the stable part (system prompt and catalog) first so the prefix can reach 1,024 tokens and be cached. Set `prompt_cache_key` to the thread id.
- `questions`:
  - one `predicate` per **non-built-in** tool, named `tool:<tool_name>`, asking "Will the agent likely need `<tool_name>` to answer this request?";
  - one `choice` named `model_tier`, with one choice per tier from `models.yaml` and a description for each.
- Selection: keep tools whose `probability >= threshold`, starting at 0.5 and configurable, capped at `max_tools`. Always keep the DeepAgents built-ins (`read_file`, `write_file`, `edit_file`, `ls`, `glob`, `grep`, `task`, `write_todos`) and anything listed in `always_include`, without asking about them.
- Fallbacks:
  - a `refusal` for a tool keeps that tool;
  - a `refusal` on `model_tier`, or a confidence below the floor, keeps the default tier;
  - a request error or an open circuit breaker keeps all tools and the default tier.
- Test fixtures: build request and response JSON from the shapes above. Replace them with a recorded real response during T9.
