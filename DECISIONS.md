# Decision log

One line per decision, with the reason. Used for the review walkthrough.

- **MCP SDK v2 (pinned `>=2.3,<3`)** — it is what `pip install mcp` gives today and what the brief's linked docs describe; v1 names (`FastMCP`) are legacy.
- **`uv` for Python** — one lockfile, reproducible install for the reviewer.
- **One backend package (`support_copilot`)** with sub-packages per concern — API and MCP server share models and retrieval code without path hacks, but run as separate processes.
- **Timestamps as ISO-8601 UTC strings** — SQLite has no datetime type; this format sorts chronologically as text and round-trips the fixtures exactly. No relative-date logic anywhere (fixture dates are fixed).
- **Chunking: 2 whole sentences per chunk, no overlap** — articles are 4–5 sentences, so this gives 2–3 chunks each (15 total). Sentences are never cut, so a condition or negation always stays with its claim. No overlap avoids the same article filling top-k with near-duplicates.
- **`text` vs `index_text` on chunks** — title and tags are added to the vectorised text to help recall, but only the chunk's own sentences are ever quoted as evidence.
- **Stable chunk IDs `KB-03#chunk-1`** — derived from article ID + position, so re-seeding gives the same IDs and citations stay valid.
- **FTS5 table is standalone and filled by the seed** — ticket text never changes after seeding (the only write is `reviewed_at`), so sync triggers would be dead code. Porter stemming for word variants.
- **FTS5 created with raw SQL inside the Alembic migration** — SQLAlchemy has no FTS5 construct; keeping it in the migration means one command builds the whole schema.
- **CHECK constraints on status and priority** — the DB itself rejects values outside the allowed set, not only the API.
- **Seed = migrate + delete + reload in one transaction** — repeatable by construction; `assistant_runs` is preserved.
- **`assistant_runs` stores no ticket or query text** — the brief asks to avoid logging ticket content.
- **TF-IDF: unigrams + bigrams, sublinear TF, English stop words minus negations** — bigrams reward phrases ("backup code", "background job"); sublinear TF stops a word repeated in title + tags + body from dominating; "not/no/never" are kept so "do not ask" survives as a feature.
- **Threshold 0.15, measured not guessed** — on the fixtures every correct top hit scores 0.22+, while the unscoped SFTP query's best wrong hit (KB-04) scores 0.13. 0.15 sits in that gap. Known miss: "reset my router" scores 0.21 on KB-05 via "reset"; Phase 6 eval quantifies this.
- **Category filter before threshold** — an off-category chunk is removed before scoring cut-off, as the data README asks; `top_score` is still returned so the UI can show *why* nothing passed.
- **Retrieval returns per-sentence scores inside each hit** — the composer runs in the API process and has no access to the vectoriser (it lives in the MCP server), so the server ships the scores and the composer stays pure.
- **Composer quotes whole sentences verbatim, never rewrites** — cutting a sentence can drop its condition ("if no transaction exists … may retry once"). Tests assert every quoted line is an exact sentence of a retrieved chunk.
- **Score picks which sentences, article order picks their sequence** — so KB-01's "if pending, do not ask for another payment" is always read before "may retry once".
- **Disclaimer rule** — a sentence matching "does not define/cover/…" is never quoted; if it is the *best* match, the result is `insufficient_evidence`. This is what passes the bank-decline-fee case, where KB-06 scores 0.22 (above threshold) only because it says it does *not* cover the topic.
- **`insufficient_evidence` is a state with a reason and zero citations** — never an empty string, never a partial answer.
- **"Facts to confirm" are mined from retrieved KB sentences (check/confirm/collect/record…), not a hand-written checklist** — keeps the summary grounded and cited; a checklist would be uncited knowledge.
- **FTS query: alphanumeric words only, each quoted, OR-joined, stop words dropped** — raw text breaks MATCH syntax; default AND returns nothing for a sentence. bm25 ranks.
- **bm25 floor of 2.0 for similar tickets** — OR-matching returns any ticket sharing one common word; on the fixtures real matches score 4.2+ and noise 1.6 or less. Calibrated on 12 tickets, so it is a documented knob, not a universal constant.
- **`TicketFilter` uses Literal enums** — invalid values fail validation before any SQL is built; column names come from the model's own field names, values are bound parameters.
- **No synonym map (MFA vs "multi-factor authentication")** — left as a documented limitation of sparse retrieval; ticket titles happen to carry the shared word "authenticator".
- **Injection defence is structural** — ticket/article text is only ever interpolated into quoted output; no code path parses it for actions, so there is nothing for an injected instruction to steer.
