"""Read-only ticket queries: fetch one, find similar resolved ones, count by filter."""

import re

from sqlalchemy import Connection, text

from support_copilot.retrieval.tfidf import STOP_WORDS
from support_copilot.schemas import (
    SimilarTicket,
    TicketCount,
    TicketFilter,
    TicketMessageView,
    TicketView,
)

_WORD = re.compile(r"[A-Za-z0-9]+")

# Measured on the fixtures: real matches score 4.2+, one-common-word matches 1.6 or less.
MIN_BM25_SCORE = 2.0


def build_fts_query(user_text: str) -> str | None:
    """Turn free text into a safe FTS5 MATCH expression, or None if nothing is searchable.

    Raw text cannot be passed to MATCH: `-`, `"`, `^` and words like AND/NEAR are
    query syntax. We keep only alphanumeric words and quote each one, so every
    term is a plain string. Terms are OR-joined because FTS5 ANDs by default and
    a whole sentence would then match nothing; bm25 ranks tickets sharing more
    (and rarer) terms first.
    """
    terms: list[str] = []
    for word in _WORD.findall(user_text.lower()):
        if len(word) > 1 and word not in STOP_WORDS and word not in terms:
            terms.append(word)
    return " OR ".join(f'"{t}"' for t in terms) if terms else None


def search_resolved_tickets(
    conn: Connection,
    query: str,
    exclude_ticket_id: str | None = None,
    category: str | None = None,
    limit: int = 3,
) -> list[SimilarTicket]:
    match = build_fts_query(query)
    if match is None:
        return []
    rows = conn.execute(
        text(
            """
            SELECT t.id, t.title, t.category, t.resolution_summary, bm25(tickets_fts) AS rank
            FROM tickets_fts
            JOIN tickets t ON t.id = tickets_fts.ticket_id
            WHERE tickets_fts MATCH :match
              AND t.status = 'resolved'
              AND (:exclude IS NULL OR t.id != :exclude)
              AND (:category IS NULL OR t.category = :category)
            ORDER BY rank, t.id
            LIMIT :limit
            """
        ),
        {"match": match, "exclude": exclude_ticket_id, "category": category, "limit": limit},
    )
    # bm25() is "lower is better"; negate it so a bigger score means a better match.
    # OR-matching returns any ticket sharing one common word, so weak matches are dropped.
    return [
        SimilarTicket(
            ticket_id=r.id,
            title=r.title,
            category=r.category,
            resolution_summary=r.resolution_summary or "",
            score=round(-r.rank, 4),
        )
        for r in rows
        if -r.rank >= MIN_BM25_SCORE
    ]


def count_tickets(conn: Connection, filters: TicketFilter) -> TicketCount:
    # Column names are fixed here; values are validated enums bound as parameters.
    active = filters.model_dump(exclude_none=True)
    where = " AND ".join(f"{column} = :{column}" for column in active) or "1 = 1"
    ids = conn.execute(text(f"SELECT id FROM tickets WHERE {where} ORDER BY id"), active).scalars().all()
    return TicketCount(count=len(ids), ticket_ids=list(ids))


def get_ticket(conn: Connection, ticket_id: str) -> TicketView | None:
    row = conn.execute(
        text(
            "SELECT id, title, description, category, priority, status, resolution_summary "
            "FROM tickets WHERE id = :id"
        ),
        {"id": ticket_id},
    ).one_or_none()
    if row is None:
        return None
    messages = conn.execute(
        text("SELECT at, author, text FROM ticket_messages WHERE ticket_id = :id ORDER BY position"),
        {"id": ticket_id},
    )
    return TicketView(
        **row._mapping,
        messages=[TicketMessageView(**m._mapping) for m in messages],
    )
