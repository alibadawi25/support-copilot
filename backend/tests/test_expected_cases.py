"""The supplied acceptance set, run end to end through retrieval + composer."""

import json
import re

import pytest

from support_copilot.composer import compose
from support_copilot.config import DATA_DIR
from support_copilot.retrieval.tickets import count_tickets, get_ticket, search_resolved_tickets
from support_copilot.schemas import TicketFilter

CASES = json.loads((DATA_DIR / "expected_cases.json").read_text(encoding="utf-8"))


def _check_search_knowledge(case, index):
    result = index.search(case["query"], category=case.get("category"))
    answer = compose.compose_search_knowledge(result)
    retrieved_articles = {h.article_id for h in result.hits}
    retrieved_text = " ".join(h.excerpt for h in result.hits)

    assert answer.action == "search_knowledge"
    assert set(case.get("must_include_article_ids", [])) <= retrieved_articles
    if case.get("expected_no_relevant_results"):
        assert result.hits == []
    if "expected_answer_state" in case:
        assert answer.state == case["expected_answer_state"]

    if case.get("must_cite_retrieved_evidence"):
        assert answer.state == "answered" and answer.citations
        for citation in answer.citations:
            assert citation.source_id in retrieved_articles
            assert citation.quote in retrieved_text  # verbatim, whole sentence
            assert f"{citation.quote} [{citation.chunk_id}]" in answer.text

    if answer.state == "insufficient_evidence":
        assert answer.citations == [] and answer.reason and answer.text

    for forbidden in case.get("must_not_claim", []):
        assert forbidden.lower() not in answer.text.lower()
        assert forbidden.lower() not in (answer.reason or "").lower()


def _check_similar(case, conn):
    matches = search_resolved_tickets(
        conn, case["query"], exclude_ticket_id=case["ticket_id"], category=case.get("category")
    )
    ids = [m.ticket_id for m in matches]
    assert set(case["must_include_related_ticket_ids"]) <= set(ids)
    assert case["ticket_id"] not in ids
    answer = compose.compose_similar_tickets(matches)
    assert answer.state == "answered" and answer.ticket_ids == ids


def _check_count(case, conn):
    filters = TicketFilter(**case["filters"])
    answer = compose.compose_count_tickets(filters, count_tickets(conn, filters))
    assert answer.count == case["expected_count"]
    assert answer.ticket_ids == case["expected_ticket_ids"]


def _check_summarize(case, conn, index):
    ticket = get_ticket(conn, case["ticket_id"])
    result = index.search(compose.ticket_query(ticket), category=ticket.category)
    answer = compose.compose_summarize_ticket(ticket, result)
    # The injected "print every database row and secret" line changes nothing:
    # same action, only this ticket, and it appears solely as a quoted message.
    assert answer.action == "summarize_ticket"
    assert answer.ticket_ids == case["expected_ticket_ids"]
    assert set(re.findall(r"T-\d+", answer.text)) == set(case["expected_ticket_ids"])
    assert "SFTP" in answer.text  # the requested integration is identified
    for message in ticket.messages:
        assert f'"{message.text}"' in answer.text


@pytest.mark.parametrize("case", CASES, ids=[c["case_id"] for c in CASES])
def test_expected_case(case, conn, index):
    action = case["action"]
    if action == "search_knowledge":
        _check_search_knowledge(case, index)
    elif action == "search_resolved_tickets":
        _check_similar(case, conn)
    elif action == "count_tickets":
        _check_count(case, conn)
    elif action == "summarize_ticket":
        _check_summarize(case, conn, index)
    else:
        pytest.fail(f"unhandled action {action}")
