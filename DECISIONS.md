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
