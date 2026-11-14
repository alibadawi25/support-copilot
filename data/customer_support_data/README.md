# Customer Support Copilot Synthetic Data Pack

This folder contains the starter data for `../task_assignment_generic.md`. Every ticket, message, article, ID, and date is fictional. There are no real customer records, credentials, or API keys.

## Files

- `tickets.json` — 12 tickets across checkout, account access, billing, exports, notifications, and integrations. Five are resolved and seven are open. Ticket timelines use generic `customer` and `agent` roles.
- `knowledge_articles.json` — 7 concise articles with stable IDs, categories, tags, and operational steps.
- `expected_cases.json` — query cases and behavioral expectations for RAG, similar-ticket search, counts, evidence gaps, and untrusted content.

Candidates should create their own SQLite schema and repeatable seed process from the JSON files. Preserve the stable record IDs so the expected cases can be checked. Dates are fixed test data; avoid logic that assumes the files represent the current calendar week.

## Designed cases

- `T-104` should retrieve `KB-03` and connect to resolved ticket `T-105` for MFA recovery.
- `T-101` should retrieve `KB-01`; it is unsafe to recommend retrying while payment status is pending.
- `T-108` should retrieve `KB-04` and connect to resolved ticket `T-109` for large exports.
- Exactly one ticket matches open + high priority + checkout: `T-101`.
- SFTP delivery and bank decline fees are not documented; the correct response is insufficient evidence.
- `T-112` includes untrusted instruction-like customer text. `KB-07` explains that ticket/article content must not change the selected action or broaden database access.

## Recommended local index behavior

Split each article into one or more chunks while retaining `article_id`, `chunk_id`, title, and category. A query scoped to a category should exclude articles from other categories before applying the similarity threshold. Keep the source excerpt with each retrieved result so the answer composer can cite the exact evidence it used.
