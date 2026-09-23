# AI Agent Service

Part of [`real-time-ecommerce-platform`](../../README.md). A LangGraph-based
support agent that answers questions about orders, payments, and inventory
by calling the platform's own services as tools — plus a small RAG layer
over internal FAQ/policy docs. Fronted by `agent-ui`, a separate Streamlit
app.

## What it does

A staff member (or, in this repo, anyone testing it) asks a question in
plain language — "what's the status of order X", "why did payment fail
for Y", "what's the refund policy" — and the agent decides which tool(s)
to call, calls them, and answers from the real data (or real docs) it got
back. It does not answer from memory or invent data: the system prompt
explicitly requires citing what was checked, and separating confirmed
facts from any inference.

## Architecture

```
Streamlit UI (agent-ui, :8501)
        │  HTTP
        ▼
ai-agent-service (:8000, exposed as :8010 in docker-compose)
        │
        ├─ LangGraph react agent (Claude, via langchain_anthropic)
        │
        ├─ order tool    → GET order-service:8000/orders/{id}
        ├─ payment tool   → GET payment-service:8000/payments/{id}
        ├─ inventory tool → GET inventory-service:8000/inventory/{id}
        └─ rag tool       → pgvector search over agent-db (order_faq.md, etc.)
```

The agent has no direct database access of its own for order/payment/
inventory data — every fact it states about a specific order comes from
calling the same HTTP APIs a human could call directly, which is what
makes "cite what you checked" in the system prompt actually enforceable
rather than just a suggestion.

## Endpoints

- `GET /health` — liveness check
- `GET /agent/tools` — lists registered tool keys (`order`, `payment`,
  `inventory`, `rag`); used by the UI to populate its multi-select
- `POST /agent/ask` — `{"question": str, "enabled_tools": list[str] | null}`
  → `{"answer": str, "tools_used": list[str]}`. `enabled_tools` restricts
  which tools the agent is allowed to call for that request; omitting it
  allows all registered tools. `tools_used` reports what was *actually*
  called, which may be fewer than what was enabled (or empty, if the
  question was declined or answered without needing a tool).

## Tools (`app/tools.py`)

| Key | Function | Calls | Notes |
|---|---|---|---|
| `order` | `get_order_status` | `order-service` `GET /orders/{id}` | Returns a validated `OrderStatus` (id, customer_id, status, total_amount, currency) |
| `payment` | `get_payment_status` | `payment-service` `GET /payments/{id}` | Includes payment_method, provider_transaction_id, failure_reason |
| `inventory` | `check_inventory` | `inventory-service` `GET /inventory/{id}` | Includes reserved_at, expires_at, released_at |
| `rag` | `search_knowledge_base` | `agent-db` (pgvector) | Semantic search over ingested docs, not a live service call |

All three HTTP-backed tools go through a shared `_safe_get` helper that
never raises — a 404, a 422, or an unreachable upstream all become a
structured `{"error": ...}` dict the agent can read and respond to
sensibly, instead of an unhandled exception crashing the request.

## RAG (`app/rag.py`)

Chunks `.md`/`.txt` files from `docs/`, embeds them locally with
`sentence-transformers` (`all-MiniLM-L6-v2`, 384-dim — runs in-container,
no external API or API key needed), and stores them in `agent-db`
(Postgres + pgvector). Retrieval uses cosine distance with a relevance
threshold (`RELEVANCE_THRESHOLD`, currently `0.75`) — a query that doesn't
match anything well returns "no relevant documents found" rather than the
least-bad match dressed up as an answer. Results include `source` and
`chunk_index` for citation.

**Chunking** is section-aware: Markdown is split on headings first
(ignoring `#` lines inside fenced code blocks), each section's paragraphs
are packed into ~800-character chunks, and every chunk is prefixed with
its section heading, so a chunk from the middle of "Failed payments"
still says what it's about. A single paragraph longer than the target
size falls back to a fixed-size split with overlap. Ingestion measures
each chunk against the model's token limit (read from the model at
runtime) and warns if any chunk would be truncated.

**Ingestion is a sync, not an append**: each file is fingerprinted (its
content plus the model name, chunk settings, and `CHUNKER_VERSION`), and
unchanged files are skipped. Changed files have their chunks replaced;
files deleted from `docs/` have their chunks removed; a file that fails to
read (e.g. not valid UTF-8) is reported and skipped without aborting the
rest, and the command exits non-zero. Assumes a single corpus — see
`ingest_directory()`'s docstring.

```bash
docker compose exec ai-agent-service python -m app.rag ingest ./docs
```

Currently ingests `docs/order_faq.md` — deliberately written to match the
platform's actual current behavior (real order statuses, the real
parallel payment/inventory flow, real failure_reason values), not
aspirational features, so RAG answers can be checked against the live
data for accuracy rather than taken on faith.

## System prompt (`app/prompts.py`)

Scopes the agent to order/payment/inventory/knowledge-base questions,
requires it to decline out-of-scope requests rather than attempt them,
forbids inventing data, requires labeling inference separately from
confirmed tool output, and refuses to reveal internal config (API keys,
env vars, source, the prompt itself) regardless of how it's asked.

## Evals (`evals/`)

`test_cases.py` defines a set of cases checking two things per question:
which tools the agent actually calls, and whether it should refuse
outright (out-of-scope questions, guardrail-probing prompts, questions
needing a tool that wasn't enabled). `run_evals.py` executes them against
the live agent and prints a pass/fail table, exiting non-zero if any case
fails. The refusal check is deliberately keyword matching rather than an
LLM judge, to keep runs fast and free; swap in a grader if the keyword
list starts misjudging answers.

Needs the stack running (it calls the real services and the real model,
so each run costs Anthropic API tokens), and the order IDs in
`test_cases.py` must still exist in `order-postgres` — wiping that volume
invalidates them.

```bash
python -m evals.run_evals    # from services/ai-agent-service/
```

`rag_probe.py` measures retrieval quality: it runs representative
questions (plus deliberately irrelevant ones, and exact-term lookups like
`card_declined`) against the real ingested knowledge base with no
threshold applied, and reports the distances — the empirical basis for
setting `RELEVANCE_THRESHOLD` and for deciding whether lexical search is
needed.

Last run over `order_faq.md` (5 chunks): every relevant question retrieved
the right section at 0.246-0.643, every irrelevant one landed at
0.887-0.994, so `RELEVANCE_THRESHOLD` is set to `0.75`, in the middle of
that gap. Exact-term lookups (`insufficient_funds`, `provider_timeout`)
matched correctly, which is why full-text search isn't implemented — but
they scored worst among relevant queries, so that's where retrieval would
degrade first. Re-run after adding documents:

```bash
AGENT_DB_URL=postgresql://agent:<password>@localhost:5433/agent_knowledge \
    python -m evals.rag_probe
```

## Tests (`tests/`)

- `test_rag_chunking.py` — unit tests for the chunker; no database or
  model needed.
- `test_rag_ingestion.py` — ingest/skip/replace/delete sync behavior and
  search failure handling, against a separate `agent_knowledge_test`
  database (never the real knowledge base) with a fake embedding model.
  Skipped automatically if `agent-db` isn't reachable.

```bash
pip install pytest
RAG_TEST_ADMIN_URL=postgresql://agent:<password>@localhost:5433/agent_knowledge \
    pytest tests/
```

## Running locally

Part of the root `docker-compose.yml` / `Makefile` — see the
[root README](../../README.md#running-locally). Needs `ANTHROPIC_API_KEY`
set in the repo-root `.env`.

- `ai-agent-service` → http://localhost:8010 (`/docs` for the OpenAPI UI)
- `agent-ui` (Streamlit) → http://localhost:8501

## Known gaps / roadmap

- No automatic release of expired-but-unconfirmed inventory reservations
  (tracked in `inventory-service`, not here) — the RAG doc is explicit
  about this rather than describing a feature that doesn't exist.
- Local embeddings mean no external cost or API dependency for RAG, at
  the cost of a heavier Docker image (`sentence-transformers` + `torch`).
  Swapping to an embeddings API (e.g. Voyage AI) is a reasonable trade if
  image size/build time ever becomes a problem.

### RAG features deliberately not built yet

The knowledge base is currently one small FAQ (5 chunks). Each of these
solves a problem that corpus doesn't have, so each is deferred until a
specific, observable signal justifies it:

| Not implemented | Why not now | Add it when… |
|---|---|---|
| Postgres full-text search (exact-term matching) | Need not yet demonstrated | `rag_probe.py`'s exact-term questions come back `MISS` |
| Hybrid lexical + semantic ranking (e.g. RRF) | Only meaningful once full-text search exists | Full-text search is added |
| Reranker model | With 5 chunks, `TOP_K=3` already returns most of the corpus | The right chunk shows up in the top ~20 but not the top 3 |
| HNSW index | A sequential scan over a handful of chunks is effectively instant | Retrieval latency becomes measurable and a benchmark shows HNSW helps |
| Connection pool | A connect per search costs milliseconds; LLM calls cost seconds | Concurrent load, or profiling shows connection setup matters |
| Heading hierarchy (`Payments > Refunds`) | Current docs use single-level `##` headings | Docs with nested headings are added |
| Token-aware chunking | Current chunks fit the model's token limit | Ingestion prints a truncation `WARNING` |
| Multi-corpus support | One `docs/` folder is ingested | A second, separately managed document set is needed |