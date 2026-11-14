# Decision log

One line per decision, with the reason. Used for the review walkthrough.

- **MCP SDK v2 (pinned `>=2.3,<3`)** — it is what `pip install mcp` gives today and what the brief's linked docs describe; v1 names (`FastMCP`) are legacy.
- **`uv` for Python** — one lockfile, reproducible install for the reviewer.
- **One backend package (`support_copilot`)** with sub-packages per concern — API and MCP server share models and retrieval code without path hacks, but run as separate processes.
