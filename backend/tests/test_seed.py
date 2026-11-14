from sqlalchemy import text

from support_copilot.db.seed import seed
from support_copilot.retrieval.chunking import chunk_article, split_sentences


def _snapshot(engine):
    with engine.connect() as c:
        return {
            "tickets": c.execute(text("SELECT id, reviewed_at FROM tickets ORDER BY id")).all(),
            "messages": c.execute(text("SELECT ticket_id, position, text FROM ticket_messages ORDER BY 1, 2")).all(),
            "chunks": c.execute(text("SELECT id, text FROM article_chunks ORDER BY id")).all(),
            "fts": c.execute(text("SELECT ticket_id FROM tickets_fts ORDER BY ticket_id")).all(),
        }


def test_seed_loads_the_data_pack(engine):
    snap = _snapshot(engine)
    assert len(snap["tickets"]) == 12
    assert len(snap["messages"]) == 24
    assert len(snap["fts"]) == 12
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM articles")).scalar() == 7


def test_seed_is_repeatable(engine):
    before = _snapshot(engine)
    seed()
    assert _snapshot(engine) == before


def test_chunk_ids_are_stable_and_cover_the_article(engine):
    with engine.connect() as c:
        ids = [r[0] for r in c.execute(text("SELECT id FROM article_chunks WHERE article_id='KB-03' ORDER BY chunk_index"))]
        body = c.execute(text("SELECT body FROM articles WHERE id='KB-03'")).scalar()
        texts = [r[0] for r in c.execute(text("SELECT text FROM article_chunks WHERE article_id='KB-03' ORDER BY chunk_index"))]
    assert ids == ["KB-03#chunk-1", "KB-03#chunk-2"]
    assert " ".join(texts) == body  # nothing lost, nothing invented


def test_sentences_are_never_cut():
    body = "If the payment is pending, do not ask again; wait. If no transaction exists, retry once. Note it."
    assert split_sentences(body) == [
        "If the payment is pending, do not ask again; wait.",
        "If no transaction exists, retry once.",
        "Note it.",
    ]
    assert [c.text for c in chunk_article("KB-X", body)] == [
        "If the payment is pending, do not ask again; wait. If no transaction exists, retry once.",
        "Note it.",
    ]


def test_filter_combination_matches_expected_case(engine):
    # expected_cases.json: exactly one open + high + checkout ticket, T-101.
    with engine.connect() as c:
        rows = c.execute(
            text("SELECT id FROM tickets WHERE status=:s AND priority=:p AND category=:c"),
            {"s": "open", "p": "high", "c": "checkout"},
        ).all()
    assert [r[0] for r in rows] == ["T-101"]


def test_fts_finds_resolved_mfa_ticket(engine):
    with engine.connect() as c:
        rows = c.execute(
            text(
                "SELECT f.ticket_id FROM tickets_fts f JOIN tickets t ON t.id = f.ticket_id "
                "WHERE tickets_fts MATCH :q AND t.status = 'resolved' ORDER BY bm25(tickets_fts)"
            ),
            {"q": '"authenticator" OR "phone" OR "replaced"'},
        ).all()
    assert rows[0][0] == "T-105"


def test_constraints_reject_bad_enum_values(engine):
    import pytest
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError), engine.begin() as c:
        c.execute(text("UPDATE tickets SET priority='urgent' WHERE id='T-101'"))
