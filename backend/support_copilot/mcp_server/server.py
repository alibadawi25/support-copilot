"""Read-only MCP server: thin, typed wrappers over the retrieval layer.

The server returns evidence only. Composing an answer happens in the API, so
nothing here can invent text. Run it with:

    uv run python -m support_copilot.mcp_server
"""

import json
import logging
import sys
from pathlib import Path
from typing import Annotated

from mcp.server import MCPServer
from pydantic import Field
from sqlalchemy import text

from support_copilot.config import db_path
from support_copilot.mcp_server.readonly import open_readonly_engine
from support_copilot.retrieval import tickets as ticket_queries
from support_copilot.retrieval.tfidf import KnowledgeIndex, load_chunks
from support_copilot.schemas import (
    ArticleView,
    Category,
    KnowledgeSearchResult,
    Priority,
    SimilarTicketsResult,
    Status,
    TicketCount,
    TicketFilter,
    TicketLookup,
)

log = logging.getLogger("support_copilot.mcp")

# Input bounds. Anything outside them is rejected by the SDK before our code
# runs and reaches the client as is_error=True.
Query = Annotated[str, Field(min_length=1, max_length=500, description="Free-text search query")]
TicketId = Annotated[str, Field(pattern=r"^T-\d{1,6}$", description="Ticket ID, e.g. T-101")]
ArticleId = Annotated[str, Field(pattern=r"^KB-\d{1,6}$", description="Article ID, e.g. KB-03")]
Limit = Annotated[int, Field(ge=1, le=10, description="Maximum number of results")]


def build_server(database: Path | None = None) -> MCPServer:
    """Create the server with its read-only engine and the TF-IDF index built once."""
    engine = open_readonly_engine(database or db_path())
    with engine.connect() as conn:
        index = KnowledgeIndex(load_chunks(conn))
    log.info("knowledge index built: %d chunks", len(index.chunks))

    mcp = MCPServer("support-copilot")

    @mcp.tool()
    def get_ticket(ticket_id: TicketId) -> TicketLookup:
        """Fetch one ticket with its message timeline. Unknown IDs return found=false."""
        with engine.connect() as conn:
            ticket = ticket_queries.get_ticket(conn, ticket_id)
        return TicketLookup(found=ticket is not None, ticket=ticket)

    @mcp.tool()
    def search_knowledge(
        query: Query, category: Category | None = None, top_k: Limit = 3
    ) -> KnowledgeSearchResult:
        """Search knowledge-base chunks by TF-IDF cosine similarity.

        Only chunks at or above the server's relevance threshold are returned, so
        an empty `hits` list means "no sufficient evidence". The threshold is not
        a parameter: a caller cannot lower the bar.
        """
        return index.search(query, category=category, top_k=top_k)

    @mcp.tool()
    def search_resolved_tickets(
        query: Query,
        exclude_ticket_id: TicketId | None = None,
        category: Category | None = None,
        limit: Limit = 3,
    ) -> SimilarTicketsResult:
        """Find resolved tickets similar to the query (FTS5, bm25-ranked)."""
        with engine.connect() as conn:
            found = ticket_queries.search_resolved_tickets(
                conn, query, exclude_ticket_id=exclude_ticket_id, category=category, limit=limit
            )
        return SimilarTicketsResult(tickets=found)

    @mcp.tool()
    def count_tickets(
        status: Status | None = None,
        priority: Priority | None = None,
        category: Category | None = None,
    ) -> TicketCount:
        """Count tickets matching the given filters. Returns the count and the matching IDs."""
        filters = TicketFilter(status=status, priority=priority, category=category)
        with engine.connect() as conn:
            return ticket_queries.count_tickets(conn, filters)

    @mcp.resource("support://tickets/{ticket_id}", mime_type="application/json")
    def ticket_resource(ticket_id: TicketId) -> str:
        """One ticket as JSON."""
        with engine.connect() as conn:
            ticket = ticket_queries.get_ticket(conn, ticket_id)
        if ticket is None:
            raise ValueError(f"Unknown ticket: {ticket_id}")
        return ticket.model_dump_json()

    @mcp.resource("support://knowledge/{article_id}", mime_type="application/json")
    def article_resource(article_id: ArticleId) -> str:
        """One knowledge-base article as JSON."""
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id, title, category, tags, updated_at, body FROM articles WHERE id = :id"),
                {"id": article_id},
            ).one_or_none()
        if row is None:
            raise ValueError(f"Unknown article: {article_id}")
        # `tags` is a JSON column; raw SQL returns it as its stored string.
        return ArticleView(**{**row._mapping, "tags": json.loads(row.tags)}).model_dump_json()

    return mcp


def main() -> None:
    # stdout carries the JSON-RPC stream, so every log line must go to stderr.
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s")
    build_server().run(transport="stdio")
