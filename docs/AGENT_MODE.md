# Agent mode (Phase 1.5)

Today the bot is a parser: text goes through a keyword heuristic, then one of two fixed
prompts, and the model returns JSON that Python writes into the sheet. It can only
record. This document plans the next step — letting the bot **answer questions about
the data** and accept free-form instructions — using Claude's tool use.

Status: **planned, not built.** Written 2026-08-20.

## Why it's not a rewrite

`bot/sheets.py` is already a tool layer: ~20 functions with clean signatures, all taking
`sheet_id` first. Tool use needs a schema per function and a loop — nothing about the
sheet layer or the category model changes.

```
now:    text -> is_income() regex -> 1 of 2 prompts -> _extract() -> sheets.*
agent:  text -> one request with tools -> tool_use block -> sheets.* -> reply
```

Two existing weak spots disappear on the way:

- `is_income()` routes on a keyword list. Commit `359927b` fixed a gift/savings expense
  landing in income — a bug this heuristic causes by construction. Choosing between an
  `add_expense` and an `add_income` tool is a semantic decision, not a substring match.
- `parser._extract()` finds JSON by scanning for `[` and `{` in the model's prose. With
  `strict: true` on a tool definition the API guarantees the arguments validate against
  the schema, so the hand-rolled extraction goes away.

## Three modes = three tool sets

Modes are not a menu the user toggles through. They are which tools get put in the
`tools` array, which makes read-only an actual boundary rather than an instruction.

| Mode | Tools | Chosen by |
|---|---|---|
| Record | `add_expenses`, `add_income`, `add_debt`, `repay_debt` | the model, from the message |
| Ask | `query_spending`, `query_income`, `list_debts` | the model, from the message |
| Read-only | read tools only; write tools absent from the request | the user, explicitly |

If a write tool is not in `tools`, no prompt injection and no hallucination can write to
the sheet. Read-only is also the safe way to demo the bot.

## Rules that keep it cheap and safe

**Aggregate in Python, never in the model.** A read tool returns
`{"total": 432.10, "count": 23, "period": "2026-09"}` — about 30 tokens. Returning the
matching journal rows instead would be ~10K tokens, cost 7x more per question, and put
the whole journal in the model's context. This single decision drives both the token
bill and the privacy exposure.

**`sheet_id` is never a tool parameter.** It is bound in Python from
`store.get_sheet(user_id)` before the tool is exposed. If the model could name a sheet,
a bad tool call could read someone else's data. Access control belongs in code, never in
a system prompt.

**Numbers are formatted by Python.** The model receives a rendered string and wraps it
in prose. A model that computes its own totals will occasionally be confidently wrong,
and nobody checks a plausible number.

**Read tools return numbers, not free text.** `note` fields are user-authored and can
carry instructions; keeping them out of tool results removes the injection surface.

**The loop is bounded.** Three iterations maximum, `max_tokens` set per call, plus a
per-user daily request counter in `store.py`.

## Cost

Measured, not estimated: the current expense system prompt is **832 tokens** (29
categories plus rules). With tool schemas a request is roughly 1400–1600 input tokens.

| Model | Input $/1M | Output $/1M | Per message¹ | 30 msg/day |
|---|---|---|---|---|
| Haiku 4.5 | $1 | $5 | ~$0.002 | ~$1.9/mo |
| Sonnet 5 | $3 | $15 | ~$0.007 | ~$6/mo |
| Opus 5 | $5 | $25 | ~$0.013 | ~$11/mo |

¹ 1500 in + 200 out, single round trip. A read question needs two (call → tool result →
answer), so multiply by ~1.8.

**Prompt caching will not help here.** The minimum cacheable prefix is ~1024 tokens, so
the prompt barely qualifies — but the ephemeral cache TTL is 5 minutes and this bot gets
a message every few hours. Budget at full price; do not plan around cache hits.

Suggested split: **Haiku on the write path** (narrow, already proven) and **Sonnet 5 or
Opus 5 on the read path** with `effort: "low"`, where a wrong period silently produces a
wrong number.

## Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | Anthropic key leaking to the model | Negligible | — | The key travels in a header; the model never sees it |
| 2 | One user reading another's sheet | Low, **but the worst case** | Critical | Bind `sheet_id` server-side; keep it out of every tool schema |
| 3 | Prompt injection via sheet contents | Medium | Medium | Read tools return aggregates, not `note` text; writes always confirm |
| 4 | Unbounded loop burning the API budget | Medium | Medium | Iteration cap, `max_tokens`, per-user daily quota, and the access gate |
| 5 | Google Sheets API quota | Medium, grows with users | Medium | One service account serves everyone, so the project quota is shared. An agent makes 2–4 full-sheet reads per question — cache journal rows in memory for ~60s |
| 6 | Hallucinated totals | Medium | High, and silent | Python computes and formats; the model only narrates |
| 7 | Expense data reaching Anthropic | Certain, by design | Low | Already true of the parser. API data is not trained on and is retained 30 days |

Risks 2 and 4 are not LLM problems — they are ordinary authorization and rate-limiting
bugs, fixed in code.

## User stories

### Epic A — Foundation

- **A1** — `bot/agent.py` with a tool-use loop capped at 3 iterations, so the model can
  call tools but cannot spin. *(~0.5 d)*
- **A2** — A tool registry where `sheet_id` is bound from `store` in Python and absent
  from the JSON schema, so no tool call can address another user's sheet. *(~0.5 d, critical)*
- **A3** — A per-user daily request counter in `store.py`, so an approved user cannot
  drain the API budget. *(~0.5 d)*
- **A4** — Structured logging of every tool call (user, tool, arguments, duration) with
  no raw amounts, for debugging and spotting anomalies. *(~0.5 d)*

### Epic B — Read-only assistant

- **B1** — Ask "how much did I spend last week" and get a compact answer. *(~1 d)*
- **B2** — Understand periods: "in September", "on 12 March", "the last 3 months". The
  tool takes `(start, end)`; resolving the phrase is the model's job. *(~0.5 d)*
- **B3** — Filter by category and place: "how much on groceries in September". *(~0.5 d)*
- **B4** — A fixed compact answer format — total, breakdown, comparison with the previous
  period — formatted in Python. *(~0.5 d)*
- **B5** — Cache journal rows in memory for 60s per user, so a 3-tool answer is not 3
  full sheet reads. *(~0.5 d)*

### Epic C — Free-form writing

- **C1** — "add 100 eur for car repair and 200 for groceries" produces two correct rows.
  Largely the current prompt moved into a tool schema. *(~1 d)*
- **C2** — Keep the confirmation step before a multi-item write. *(~0.5 d)*
- **C3** — Keep the follow-up questions (liters for fuel, place for groceries) working
  inside the tool loop. The fiddliest part of the whole plan. *(~1 d)*
- **C4** — Fall back to the current deterministic parser when the API call fails. *(~0.5 d)*

### Epic D — Modes and safety

- **D1** — A read-only switch that omits write tools from the request entirely. *(~0.5 d)*
- **D2** — Read tools return aggregates only, never raw `note` text. *(~0.5 d, part of A2)*
- **D3** — `undo` and any delete stay out of the agent's tool set — explicit commands
  only, so a conversation can never erase data. *(~0.25 d)*

Rough total **~9–10 days**, of which Epics A and D (~3 days) are the foundation and
cannot be deferred.

## Order of work

Do not start with Epic C. It holds the hardest piece (C3, follow-up state inside the
tool loop) and delivers the least: the current parser already handles most of it.

Start with **A1–A4 plus B1–B2 in read-only**. New code physically cannot damage the
sheet, the loop and the prompt get proven on a safe surface, the real token cost becomes
measurable, and there is a working feature at the end of it — roughly 3 days. Writing
comes second, once the foundation holds.

Risk 5 (Sheets quota) is the first concrete argument for the Phase 2 database move. Do
not migrate yet, but build the B5 cache so it can later be swapped for a different data
source rather than removed.
