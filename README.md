# Support Copilot

An offline support copilot. An agent picks a ticket, runs one of five fixed actions, and gets an answer built only from sentences that exist in the local knowledge base or ticket history, each with a citation. There is no language model at runtime, no API key and no external service.

```
React + TypeScript (Vite, :5173)
   │  REST/JSON through the Vite dev proxy
FastAPI (:8000) ── Pydantic contracts, validation, run log, response composer
   │  ├── SQLAlchemy, read/write: ticket list/detail, "reviewed" flag, assistant_runs
   │  └── MCP client over stdio ──► MCP server (child process, read-only)
   │                                   ├── tools: get_ticket, search_knowledge,
   │                                   │          search_resolved_tickets, count_tickets
   │                                   └── resources: support://tickets/{id},
   │                                                  support://knowledge/{id}
   └────────────── both open the same SQLite file ──────────────┘
                   (tickets, messages, articles, article_chunks, tickets_fts, assistant_runs)
```

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- Node.js 20.19+ or 22.12+ (required by Vite 8) and npm
- Network access for the two install steps only. Nothing below needs it afterwards.

## Quick start

Terminal 1, backend:

```bash
cd backend
uv sync
uv run python -m support_copilot.db.seed
uv run uvicorn support_copilot.api.main:app
```

Terminal 2, frontend:

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173.

- The seed step creates `backend/support_copilot.db`, applies the Alembic migration and loads `data/customer_support_data/*.json`. It must run before the API starts. It is safe to re-run: the fixture tables are reloaded and chunk IDs stay the same.
- The API starts the MCP server itself as a child process (`python -m support_copilot.mcp_server`) and keeps one stdio session open for its lifetime. You do not start the MCP server by hand.
- `http://localhost:8000/health` should return `{"status":"ok","database":true,"mcp_ready":true}`. API docs are at `http://localhost:8000/docs`.
- The frontend expects the API on port 8000 (see `frontend/vite.config.ts`).
- `SUPPORT_COPILOT_DB` overrides the database path. It is optional.

## Sample actions

In the UI: pick a ticket in the queue, choose an action in the assistant panel, run it.

| Try | Expect |
|---|---|
| T-101 → Draft reply | A draft marked "not sent", quoting KB-01 and KB-02. It says not to ask for another payment while one is pending. |
| Search knowledge: `lost authenticator after replacing phone; backup code and enroll a new device`, category `account_access` | Answer cited to KB-03 |
| Search knowledge: `Does the product reimburse a bank decline fee?`, category `billing` | Insufficient evidence. KB-06 matches, but only in a sentence saying it does not cover the topic. |
| Search knowledge: `Configure scheduled SFTP delivery of reports to an external server`, category `integrations` | Insufficient evidence. No article covers it. |
| T-101 → Find similar resolved tickets | T-103, with its resolution |
| Count tickets, status `open` | 7 tickets, listed by ID |
| T-112 → Summarize ticket | The ticket's injected instruction appears only as quoted text |
| Draft reply with no ticket selected | The server's validation message |

The same call with curl (bash or Git Bash quoting):

```bash
curl -s -X POST http://localhost:8000/api/assistant/run -H "content-type: application/json" -d '{"action":"draft_reply","ticket_id":"T-101"}'
```

Every response carries `run_id`, `answer` (state, text, citations), `retrieval` (method, top-k, threshold, top score), `tool_trace` (the MCP tools that were called) and `limitations`.

## Data flow for one question

1. The UI posts `{action, ticket_id?, query?, category?, filters?}` to `POST /api/assistant/run`.
2. `AssistantRequest` validates it. Unknown fields, unknown actions and missing per-action fields are a 422 before any tool runs.
3. `api/assistant.py` runs the fixed flow for that action. The action alone decides which MCP tools are called. Ticket and article text only travels as tool arguments or quoted evidence.
4. The MCP client calls the tool over stdio. The server queries SQLite on a read-only connection and returns typed evidence: chunks with scores and per-sentence scores, or tickets, or a count. It never returns answer text.
5. `composer/compose.py` builds the answer from whole evidence sentences, in article order, each tagged with its chunk ID. If nothing clears the threshold, or the best match is a disclaimer, the state is `insufficient_evidence` with a reason and no citations.
6. The API writes a row to `assistant_runs` (run ID, action, tools, retrieval method, state, success, duration; no query or ticket text) and returns the response.

## Retrieval and the index

- **Chunking** (`retrieval/chunking.py`): two whole sentences per chunk, no overlap. 7 articles give 15 chunks. Sentences are never cut, so a condition stays with its claim. Chunk IDs are stable: `KB-03#chunk-1`.
- **Index build**: chunks are stored in SQLite by the seed. The TF-IDF matrix is not stored. The MCP server builds it in memory from `article_chunks` each time it starts, which takes milliseconds at this size. To rebuild after changing the data: re-run the seed, then restart the API.
- **Vectoriser** (`retrieval/tfidf.py`): scikit-learn TF-IDF, unigrams and bigrams, sublinear TF, English stop words with negations kept. Title and tags are added to the indexed text; only the chunk's own sentences are ever quoted.
- **Scoring**: cosine similarity, optional category filter, top 3. Query words the index has never seen count against the score, so one matching word in an off-topic question does not pass.
- **Threshold**: 0.17, chosen from the sweep below. Callers cannot lower it.
- **Similar tickets**: SQLite FTS5 over resolved tickets, ranked by BM25, with a floor of 2.0.

### Evaluation

```bash
cd backend
uv run python -m support_copilot.eval
```

23 labelled queries (15 answerable, 8 with no answer in the knowledge base).

| Ranking, unscoped | hit@1 | hit@3 | MRR |
|---|---:|---:|---:|
| TF-IDF cosine | 0.71 | 0.93 | 0.82 |
| FTS5 BM25 | 0.71 | 0.93 | 0.82 |

| Threshold | Correct | False accept | False reject | Wrong source |
|---:|---:|---:|---:|---:|
| 0.10 | 16 | 2 | 3 | 2 |
| 0.15 | 18 | 0 | 4 | 1 |
| **0.17** | 17 | 0 | 6 | 0 |
| 0.25 | 17 | 0 | 6 | 0 |
| 0.30 | 16 | 0 | 7 | 0 |

0.17 is the lowest setting with no false accept and no answer cited to the wrong article. The cost is six refused questions that do have an answer, all paraphrases or very short queries. 0.15 gets one more right but answers "How do I reset MFA?" from the password-reset article. The set is seven articles and hand-written queries: it shows where the index fails, not how it would score on a real knowledge base.

## MCP server

Run it alone (stdio; logs go to stderr):

```bash
cd backend
uv run python -m support_copilot.mcp_server
```

Inspect it with the MCP Inspector (needs Node and, the first time, network to fetch the Inspector):

```bash
cd backend
npx @modelcontextprotocol/inspector uv run python -m support_copilot.mcp_server
```

Or as a client configuration entry:

```json
{
  "mcpServers": {
    "support-copilot": {
      "command": "uv",
      "args": ["run", "--directory", "<path-to-repo>/backend", "python", "-m", "support_copilot.mcp_server"]
    }
  }
}
```

- **Tools**: `get_ticket`, `search_knowledge`, `search_resolved_tickets`, `count_tickets`. Inputs are bounded in the schema (ID patterns, enums, query 1–500 characters, `top_k`/`limit` 1–10). Outputs are Pydantic models.
- **Resources**: `support://tickets/{ticket_id}`, `support://knowledge/{article_id}`.
- **Read-only** at two layers (`mcp_server/readonly.py`): the file is opened with `mode=ro`, and the connection sets `PRAGMA query_only = ON`. All SQL uses bound parameters.
- **Client** (`api/mcp_gateway.py`): official SDK client, one stdio session opened in the FastAPI lifespan, 10 s timeout per call. If the server fails, assistant calls return 503, `/health` reports `mcp_ready: false`, and the ticket routes keep working. There is no automatic restart.

## Tests

```bash
cd backend
uv run pytest -q
```

```bash
cd frontend
npm test
```

134 backend tests and 2 frontend tests. The ones worth reading first:

- `tests/test_expected_cases.py`: the 10 supplied acceptance cases.
- `tests/test_grounding.py`: every quoted line in every answer must be an exact sentence from the database, checked over all eval queries, all tickets, hostile inputs and the API → MCP path.
- `tests/test_mcp_server.py`: tools, resources, bad input, and proof that writes fail.
- `tests/test_api.py`: routes, validation, and a broken MCP server giving a 503.

## Layout

```
backend/support_copilot/
  db/          models, seed          (migration in backend/alembic)
  retrieval/   chunking, TF-IDF index, ticket queries
  composer/    deterministic answer builder
  mcp_server/  read-only MCP server
  api/         FastAPI app, MCP gateway, per-action flows, REST contracts
  eval/        labelled queries, retrieval report, grounding checker
frontend/src/  api client, App, components
data/customer_support_data/   supplied fixtures and expected cases
DECISIONS.md   one line per design decision, with the reason
AI_USAGE.md    AI tools used and what was reviewed
```

## Known limitations

- **Lexical retrieval.** TF-IDF matches words, not meaning. "multi-factor authentication" does not match "MFA", and "charged twice" does not match "duplicate payment". The six false rejects above are this. Embeddings would close most of that gap; there is no synonym map.
- **The threshold is tuned on 7 articles.** 0.17 and the BM25 floor of 2.0 are measured on this data pack and would need re-measuring on any other corpus.
- **Answers are quotes, not prose.** The composer selects and orders whole sentences. It cannot merge, rephrase or answer a question whose answer spans sentences that do not score well individually. T-103 (missing receipt email) gets no draft because no article covers it.
- **Disclaimer detection is a pattern.** Sentences like "does not define…" are recognised by a fixed list of phrasings. A disclaimer written another way would be quoted as evidence.
- **No MCP restart.** If the MCP child process dies, the assistant stays unavailable until the API is restarted.
- **No authentication or roles**, and the API has no CORS policy; the frontend reaches it through the Vite dev proxy. This is a local development setup, not a deployment.
- **Single-process index.** The TF-IDF matrix lives in the MCP server's memory and is rebuilt on start. Fine for 15 chunks; a larger corpus would want a persisted index.
- **The 503 state in the UI** is covered by tests of the error mapping but was not triggered live in the browser.
