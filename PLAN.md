# Support Copilot — Project Plan

Timebox: 3–4 days. Showcase focus: **retrieval rigor** and **safety/reliability**.

How to read this: every phase has a goal, tasks, a "done when" check, and **Your call** items. The "Your call" items are deliberately left open — they are the design decisions reviewers will ask you to defend, so they should be yours.

---

## 1. What the reviewers are actually grading

| Area | Weight | Where this plan earns it |
|---|---:|---|
| RAG quality and grounding | 20% | Phase 2, Phase 6A |
| MCP design and integration | 20% | Phase 3, Phase 4 |
| Full-stack workflow | 15% | Phase 5 |
| API and data design | 15% | Phase 1, Phase 4 |
| Reliability, security, tests | 15% | Every phase, Phase 6B |
| Explanation and ownership | 15% | Phase 7, plus the decision log you keep throughout |

Two things the brief says outright: stretch features do **not** compensate for (a) a fabricated citation or (b) an app that does not run from the README. So the order of priority is: runs from README → never fabricates → required features → showcase.

## 2. Things I found that are easy to miss

These came out of reading the data pack and checking current docs. Each one is a place where a naive build fails an expected case.

1. **The MCP SDK changed.** `pip install mcp` now installs 2.x (2.3.0 on PyPI). v2 renames `FastMCP` to `MCPServer` (`from mcp.server import MCPServer`), adds a high-level `Client`, and switches result fields to snake_case. The docs the brief links to (main branch) are v2. Most tutorials and AI-generated snippets still use v1 names. v1.x (1.30) is still maintained. Recommendation: use v2, pin it, and check every snippet against the official docs. Fallback: pin `mcp<2` if the spike in Phase 0 hits a wall.
2. **A threshold alone cannot pass the "bank decline fee" case.** The query asks about bank decline fees in category `billing`. KB-06 literally contains the words "bank decline fees" — in a sentence saying the article does *not* define them. TF-IDF will score it well. The expected state is still `insufficient_evidence`, and the answer must not say the fee is or is not reimbursed. The composer needs a rule for evidence that is a disclaimer, not an answer.
3. **Sentence cutting can invert meaning.** KB-01 says "If the payment is pending, do not ask the customer to submit another payment" and later "If no transaction exists after the gateway check, the customer may retry once." Dropping a condition or truncating a sentence produces "the customer may retry" for T-101, which is the exact forbidden claim. Evidence must be quoted as whole sentences with their conditions.
4. **The SFTP case passes for a boring reason.** No article has category `integrations`, so a category-scoped search is empty before scoring. Also test it *unscoped*, where KB-04 (exports) may partly match — that is the real threshold test.
5. **Vocabulary mismatch is built into the data.** T-104 says "multi-factor authentication"; KB-03 says "MFA" and "authenticator". TF-IDF has no idea these are related. This is your concrete example for "what sparse retrieval misses versus embeddings".
6. **FTS5 will throw on raw user text.** Characters like `-`, `"`, `^`, `@`, and words like `AND`/`NEAR` are query syntax. Natural-language queries must be tokenised and quoted before `MATCH`. Also, FTS5 ANDs terms by default, so a long question returns nothing unless you join terms with `OR`.
7. **stdio session lifetime in FastAPI.** The MCP stdio client uses anyio task groups; it must be entered and exited in the same task. Open it once in the FastAPI lifespan (one `AsyncExitStack`), not per request and not in a dependency.
8. **Dates are fixture data.** The data README warns against logic that assumes "this week". No relative-date filters.

## 3. Architecture

```
React + TS (Vite)
   │  REST (JSON)
FastAPI ── Pydantic contracts, validation, run logging
   │  ├── direct SQLAlchemy: ticket list/detail, PATCH reviewed, assistant_runs   (read/write)
   │  └── MCP client over stdio ──► MCP server process                            (read-only)
   │                                   ├── tools: get_ticket, search_knowledge,
   │                                   │          search_resolved_tickets, count_tickets
   │                                   ├── resources: support://tickets/{id}, support://knowledge/{id}
   │                                   ├── TF-IDF index (in memory, built at startup from chunks table)
   │                                   └── SQLite opened read-only
   └── Response composer (pure Python, no I/O): evidence in → cited answer or insufficient_evidence out
```

Rule that keeps the boundary honest: anything the assistant *reads* for an action goes through MCP. FastAPI touches the DB directly only for the queue UI, the one write route, and run metadata.

Suggested layout:

```
backend/
  app/            FastAPI: main, routes, schemas, mcp_client, composer/, runs
  mcp_server/     server.py, tools, resources, readonly db access
  retrieval/      chunking, tfidf index, fts query builder   (pure, unit-testable)
  db/             models, alembic/, seed.py
  eval/           labelled queries, metrics, report
  tests/
frontend/         Vite + React + TS
data/             the supplied JSON (unzipped, unchanged)
README.md  AI_USAGE.md  DECISIONS.md
```

## 4. Phases

### Phase 0 — Setup and de-risking spike (about 2 hours)

Goal: prove the riskiest plumbing before building on it.

- Git repo, Python 3.11+ venv, pinned dependencies, Vite React-TS scaffold.
- Spike: a 20-line MCP server with one tool, launched over stdio from a 20-line client, on your Windows machine. Then open it in the MCP Inspector (`mcp dev`).
- Confirm your Python's SQLite has FTS5 (`SELECT fts5(?)` or create a throwaway virtual table).
- Start `DECISIONS.md` and `AI_USAGE.md` now and append as you go. Both are deliverables in disguise.

Done when: client calls the tool and prints the result; Inspector lists it.

Your call: SDK v2 or v1; `uv` or `pip`.

### Phase 1 — Data layer (about half a day)

Goal: a repeatable `seed` command that produces a correct database from the JSON.

- SQLAlchemy models: `tickets`, `ticket_messages`, `articles`, `article_chunks`, `assistant_runs`.
- Alembic migration(s): tables, indexes (status, priority, category, and a composite for the filter combination), and the FTS5 virtual table created with raw SQL in the migration.
- Seed script: idempotent, preserves IDs (`T-101`, `KB-03`), writes chunks with stable IDs like `KB-03#chunk-1`, populates FTS.
- `assistant_runs`: run ID, action, tools called, retrieval method, success, duration, error code. No ticket text.

Done when: delete the DB, run migrate + seed twice, get identical row counts and chunk IDs.

Your call: chunking strategy. The articles are 4–5 sentences each. Options: one sentence per chunk, sliding two-sentence window, or whole article. Each changes scores and what a citation looks like. Decide whether title and tags are part of the indexed text (helps recall) while staying out of the quoted excerpt (keeps citations honest). Also: what goes into the FTS index for tickets — title, description, messages, resolution summary?

Tests: seed is repeatable; filters by status/priority/category return the right IDs.

### Phase 2 — Retrieval and composer as pure Python (about one day — the core)

Goal: all the "thinking" works and is tested before any server exists.

Retrieval:
- TF-IDF index over chunks; query → same vector space → cosine → top-k.
- Category filter applied **before** the threshold.
- Return chunk ID, article ID, title, excerpt, score, and the threshold used.
- FTS5 query builder for similar resolved tickets: tokenise, quote, OR-join, `bm25()` ranking, `status = 'resolved'`, exclude the current ticket.
- `count_tickets` takes a typed filter object (enums only), never SQL fragments.

Composer (one function per action, evidence in, answer out):
- `search_knowledge`: whole evidence sentences, each tagged with its source ID.
- `summarize_ticket`: issue, what has been said, key facts still needed.
- `similar_tickets`: matched tickets plus their resolution summaries.
- `draft_reply`: template built only from cited sentences, labelled as a draft.
- `count_tickets`: number plus the matching IDs.
- `insufficient_evidence` as a first-class result with a reason, never an empty string.

Done when: all ten entries in `expected_cases.json` pass as a parametrised pytest, including every `must_not_claim`.

Your call (this is the richest area for your own ideas):
- TF-IDF settings: n-gram range, stop words, sublinear TF. Note that English stop-word lists drop "not" and "no" — decide whether that matters for you.
- The threshold value and how you justify it (Phase 6A gives you evidence).
- How to rank sentences inside a chunk against the query.
- How to detect disclaimer evidence (finding 2) and what the answer says in that case.
- Where "key facts still needed" come from: a per-category checklist, or mined from KB sentences such as "collect the message type and approximate request time".
- Whether to handle synonyms (finding 5) with a tiny hand-written map, or leave it as a documented limitation.

Tests (required items 1, 2, 6): known query → expected chunk ID; evidence appears in answer with citations; low score → insufficient evidence with zero citations; instruction-like text in T-112 and KB-07 changes nothing.

### Phase 3 — MCP server (about half a day)

Goal: a separate process that exposes Phase 2 through typed, read-only tools.

- Tools as thin wrappers: `get_ticket`, `search_knowledge`, `search_resolved_tickets`, `count_tickets`. Typed inputs with bounds (`top_k` range, query length), docstrings, structured outputs.
- Resource templates: `support://tickets/{ticket_id}`, `support://knowledge/{article_id}`.
- Read-only enforced twice: open SQLite with `mode=ro` URI and set `PRAGMA query_only = ON`. All queries parameterised.
- Logging to stderr only. No `print`.
- Build the TF-IDF index at server startup from the chunks table.

Done when: MCP Inspector lists four tools and two templates, and a tool call and a resource read return correct data. Save the Inspector command for the README.

Your call: whether the composer lives in FastAPI (server returns evidence, API composes — matches the brief's wording) or in the server; how unknown IDs are reported (tool error versus typed not-found result).

Tests (required item 3): in-memory or stdio client lists tools/resources, calls one tool, reads one resource; an attempted write through the server's connection fails.

### Phase 4 — FastAPI and MCP client (about half a day)

Goal: the REST API, with every assistant action going through MCP.

- Lifespan: start the MCP server with `sys.executable`, hold one session for the app's life, close it cleanly.
- Routes: `GET /health` (includes MCP readiness), `GET /api/tickets`, `GET /api/tickets/{id}`, `POST /api/assistant/run`, `PATCH /api/tickets/{id}/reviewed`.
- `action` is a closed enum. The flow per action is fixed in code; ticket and article text is only ever data.
- Response carries: answer, state, retrieval metadata (method, top_k, threshold), tool trace with timings, citations, limitations, run ID.
- Errors: 404 unknown ticket, 422 bad action/filter/oversized query, 503 for MCP start or call failure with a safe message. Stack traces to logs only.
- Write a run record for every call, success or failure.

Done when: `/docs` shows the full contract and a curl for each sample prompt in the brief returns a sensible result.

Your call: what happens when the MCP process dies mid-session (fail fast with 503, or restart once and retry); query length limit.

Tests (required items 4, 5): end-to-end action through real stdio; filters; reviewed persists; unknown ID and unsupported action rejected; MCP failure returns a safe 503.

### Phase 5 — Frontend (about one day)

Goal: the required workflow, with every state visible.

- Ticket queue with status/priority/category filters and reviewed indicator.
- Ticket detail: description, timeline, metadata.
- Assistant panel: action picker, query box for retrieval actions, answer, citations with score and expandable excerpt, tool trace.
- Draft editor: editable, copy button, permanent "Draft — not sent" label.
- Mark reviewed.
- States: loading, empty, no-evidence, validation error, API/MCP error.
- One Vitest test of a visible behaviour (for example: no-evidence state renders its message and zero citation cards).

Done when: you can run all five sample prompts from the brief by clicking, and can trigger every error state on purpose.

Your call: the whole visual design. Ideas that fit your showcase focus are in section 5.

### Phase 6 — Showcase work (about half a day; cut first if time runs short)

**6A. Retrieval evaluation harness.** One command, one printed report.
- A small labelled set: the expected cases plus your own queries, including paraphrases with little word overlap and out-of-scope questions.
- Metrics: hit@k, MRR, and for the threshold a sweep table showing false accepts versus false rejects.
- TF-IDF versus FTS5 BM25 on the same set (this is a listed stretch goal).
- Be upfront that seven articles is too few to generalise; say what the numbers do and do not show.

**6B. Grounding guarantee.** Turn "no fabrication" from a hope into an invariant.
- A checker asserting that every sentence in a composed answer is traceable to a cited chunk, run in tests over every eval query.
- The `must_not_claim` phrases as regression tests.
- An injection suite: instruction-like text in tickets, articles, and the query itself; FTS syntax characters; oversized input.

Done when: the eval report is in the README and the grounding check runs in `pytest`.

### Phase 7 — README, cold-start test, walkthrough prep (about half a day)

- README: prerequisites, quick start, sample actions, architecture and data-flow diagram, index build behaviour, MCP setup and Inspector command, limitations.
- Cold-start test: fresh clone, follow the README exactly, network off. Fix whatever breaks.
- Finish `AI_USAGE.md`: tools used, what you reviewed, changed, and tested.
- Rehearse the six review items. In particular, practise the live change (add a filter; change sentence selection) and know which files and tests move.

## 5. Room to innovate

Ideas, not requirements. Pick what you find interesting, or ignore these and do your own.

- **"Why this matched"**: show the top query terms that contributed to each chunk's score. Cheap with TF-IDF and makes the retrieval explainable on screen.
- **Score against threshold**: a bar per citation with the threshold line drawn on it, so the insufficient-evidence decision is visible, not just stated.
- **Evidence highlighting**: hover a sentence in the answer, the source sentence lights up in the excerpt.
- **Confidence bands** rather than one cutoff: confident / weak-but-shown / rejected.
- **Evidence-gap answers**: for the disclaimer case, say "KB-06 states this topic is not covered and should be escalated" — honest and still useful.
- **Draft safety lint**: flag a draft that asks for a password, a code, or promises a refund, using rules derived from the KB.
- **Eval page in the UI**, or an audit view of assistant runs.
- **A second retriever behind the same interface**, to make the "how would you evolve this" discussion concrete.

## 6. Suggested schedule

| Day | Work |
|---|---|
| 1 | Phase 0, Phase 1, start Phase 2 |
| 2 | Finish Phase 2, Phase 3, Phase 4 |
| 3 | Phase 5, start Phase 6 |
| 4 (half) | Finish Phase 6, Phase 7 |

If you only have three days: do 6B (it is mostly tests you need anyway), shrink 6A to the threshold sweep, and keep the UI plain.

## 7. Cut order if time runs short

1. UI polish and extra innovation ideas
2. TF-IDF versus FTS5 comparison
3. Eval harness beyond the threshold sweep

Never cut: the cold-start test, the expected-cases test, the Inspector check.
