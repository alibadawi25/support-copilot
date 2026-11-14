import pytest
from pydantic import ValidationError

from support_copilot.retrieval.tfidf import DEFAULT_THRESHOLD
from support_copilot.retrieval.tickets import (
    build_fts_query,
    count_tickets,
    get_ticket,
    search_resolved_tickets,
)
from support_copilot.schemas import TicketFilter

SFTP_QUERY = "Configure scheduled SFTP delivery of reports to an external server"


def test_known_query_returns_expected_chunk_first(index):
    result = index.search("lost authenticator, use a backup code and enroll a new device")
    assert result.hits[0].chunk_id == "KB-03#chunk-1"
    assert result.hits[0].score >= result.threshold == DEFAULT_THRESHOLD


def test_category_filter_is_applied_before_scoring_cutoff(index):
    query = "CSV export times out, use a background job"
    assert index.search(query).hits[0].article_id == "KB-04"
    scoped = index.search(query, category="checkout")
    assert all(h.category == "checkout" for h in scoped.hits)
    assert "KB-04" not in {h.article_id for h in scoped.hits}


def test_unscoped_sftp_query_is_rejected_by_threshold_not_by_category(index):
    """With no category, KB-04 (exports) partly matches; the threshold must reject it."""
    result = index.search(SFTP_QUERY)
    assert result.hits == []
    assert 0 < result.top_score < result.threshold


def test_hit_sentences_are_whole_sentences_of_the_excerpt(index):
    hit = index.search("PAYMENT_TIMEOUT pending payment", category="checkout").hits[0]
    assert " ".join(s.text for s in hit.sentences) == hit.excerpt


def test_fts_query_quotes_terms_and_drops_syntax():
    assert build_fts_query('export - "CSV" AND NEAR(report^2)') == '"export" OR "csv" OR "near" OR "report"'
    assert build_fts_query("the and of !!! --") is None


@pytest.mark.parametrize("hostile", ['"', "a-b ^c", "NEAR(", "x AND OR NOT", "'; DROP TABLE tickets;--", ""])
def test_similar_search_never_raises_on_raw_text(conn, hostile):
    assert isinstance(search_resolved_tickets(conn, hostile), list)


def test_similar_search_returns_only_resolved_and_excludes_current(conn):
    matches = search_resolved_tickets(conn, "CSV export background job", exclude_ticket_id="T-109")
    assert "T-109" not in [m.ticket_id for m in matches]
    for m in search_resolved_tickets(conn, "CSV export timeout checkout payment email"):
        assert get_ticket(conn, m.ticket_id).status == "resolved"


def test_similar_search_drops_weak_single_word_matches(conn):
    # "customer" appears in almost every ticket; that alone is not similarity.
    assert search_resolved_tickets(conn, "customer") == []


def test_count_filters_are_enums_only(conn):
    assert count_tickets(conn, TicketFilter()).count == 12
    assert count_tickets(conn, TicketFilter(status="resolved")).count == 5
    with pytest.raises(ValidationError):
        TicketFilter(status="open' OR 1=1 --")


def test_get_ticket_keeps_message_order_and_handles_unknown_id(conn):
    ticket = get_ticket(conn, "T-112")
    assert [m.author for m in ticket.messages] == ["customer", "customer"]
    assert get_ticket(conn, "T-999") is None
