"""API tests. `client` runs the real app: lifespan, real MCP server over stdio."""

import sys

import pytest
from fastapi.testclient import TestClient
from mcp import StdioServerParameters
from sqlalchemy import text

from support_copilot.api.main import create_app


@pytest.fixture(scope="module")
def client(seeded_db):
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def broken_client(seeded_db):
    """An app whose MCP server command exits immediately."""
    params = StdioServerParameters(command=sys.executable, args=["-c", "raise SystemExit(1)"])
    with TestClient(create_app(params)) as c:
        yield c


def run(client, **body):
    return client.post("/api/assistant/run", json=body)


def last_run(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT * FROM assistant_runs ORDER BY rowid DESC LIMIT 1")).one()


# ---- health and tickets ------------------------------------------------------


def test_health_reports_mcp_ready(client):
    assert client.get("/health").json() == {"status": "ok", "database": True, "mcp_ready": True}


def test_ticket_list_filters(client):
    everything = client.get("/api/tickets").json()
    filtered = client.get("/api/tickets", params={"status": "open", "priority": "high"}).json()
    assert 0 < len(filtered) < len(everything)
    assert all(t["status"] == "open" and t["priority"] == "high" for t in filtered)
    assert client.get("/api/tickets", params={"status": "closed"}).status_code == 422


def test_ticket_detail_and_unknown_id(client):
    detail = client.get("/api/tickets/T-101").json()
    assert detail["id"] == "T-101" and detail["messages"] and detail["description"]
    assert client.get("/api/tickets/T-999").status_code == 404
    assert client.get("/api/tickets/nonsense").status_code == 422


def test_reviewed_persists_and_can_be_cleared(client):
    marked = client.patch("/api/tickets/T-101/reviewed", json={"reviewed": True})
    assert marked.status_code == 200 and marked.json()["reviewed_at"]
    assert client.get("/api/tickets/T-101").json()["reviewed_at"] == marked.json()["reviewed_at"]
    client.patch("/api/tickets/T-101/reviewed", json={"reviewed": False})
    assert client.get("/api/tickets/T-101").json()["reviewed_at"] is None
    assert client.patch("/api/tickets/T-999/reviewed", json={"reviewed": True}).status_code == 404


# ---- assistant actions, end to end over stdio --------------------------------


def test_search_knowledge_returns_cited_answer_with_metadata_and_trace(client, engine):
    response = run(client, action="search_knowledge", query="lost authenticator after replacing phone", category="account_access")
    assert response.status_code == 200
    data = response.json()
    assert data["answer"]["state"] == "answered" and data["answer"]["citations"]
    assert data["retrieval"]["method"] == "tfidf_cosine"
    assert data["retrieval"]["top_k"] == 3 and data["retrieval"]["threshold"] > 0
    assert [c["tool"] for c in data["tool_trace"]] == ["search_knowledge"]
    assert all(c["ok"] and c["duration_ms"] >= 0 for c in data["tool_trace"])
    assert data["limitations"]

    record = last_run(engine)
    assert record.id == data["run_id"] and record.success == 1
    assert record.action == "search_knowledge" and record.answer_state == "answered"


def test_no_evidence_is_a_normal_200_with_no_citations(client):
    data = run(client, action="search_knowledge", query="How do I configure SFTP?", category="integrations").json()
    assert data["answer"]["state"] == "insufficient_evidence"
    assert data["answer"]["citations"] == [] and data["answer"]["reason"]


def test_summarize_ticket_calls_get_ticket_then_search(client):
    data = run(client, action="summarize_ticket", ticket_id="T-101").json()
    assert [c["tool"] for c in data["tool_trace"]] == ["get_ticket", "search_knowledge"]
    assert data["answer"]["ticket_ids"] == ["T-101"]


def test_draft_reply_is_marked_as_draft(client):
    data = run(client, action="draft_reply", ticket_id="T-101").json()
    assert data["answer"]["is_draft"] is True and data["answer"]["text"].startswith("DRAFT")


def test_similar_tickets_excludes_the_source_ticket(client):
    data = run(client, action="similar_tickets", ticket_id="T-101").json()
    assert data["retrieval"]["method"] == "fts5_bm25"
    assert "T-101" not in data["answer"]["ticket_ids"]


def test_count_tickets_with_filters(client):
    data = run(client, action="count_tickets", filters={"status": "open", "priority": "high"}).json()
    listed = client.get("/api/tickets", params={"status": "open", "priority": "high"}).json()
    assert data["answer"]["count"] == len(listed)
    assert data["answer"]["ticket_ids"] == [t["id"] for t in listed]
    assert data["retrieval"] is None


# ---- rejected requests -------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"action": "delete_ticket", "ticket_id": "T-101"},  # unsupported action
        {"action": "search_knowledge"},  # missing query
        {"action": "search_knowledge", "query": "x" * 501},  # oversized query
        {"action": "search_knowledge", "query": "mfa", "category": "weather"},  # bad category
        {"action": "summarize_ticket"},  # missing ticket
        {"action": "summarize_ticket", "ticket_id": "1; DROP TABLE tickets"},  # malformed ID
        {"action": "count_tickets", "filters": {"assignee": "bob"}},  # unknown filter
        {"action": "count_tickets", "filters": {"status": "closed"}},  # bad filter value
        {"action": "search_knowledge", "query": "mfa", "sql": "select 1"},  # unknown field
    ],
)
def test_invalid_requests_are_422(client, body):
    assert client.post("/api/assistant/run", json=body).status_code == 422


def test_unknown_ticket_is_404_and_recorded(client, engine):
    response = run(client, action="summarize_ticket", ticket_id="T-999")
    assert response.status_code == 404
    record = last_run(engine)
    assert record.success == 0 and record.error_code == "ticket_not_found"


# ---- MCP failure -------------------------------------------------------------


def test_mcp_failure_is_a_safe_503_and_recorded(broken_client, engine):
    assert broken_client.get("/health").json() == {"status": "degraded", "database": True, "mcp_ready": False}
    assert broken_client.get("/api/tickets/T-101").status_code == 200  # direct reads still work

    response = run(broken_client, action="search_knowledge", query="reset MFA")
    assert response.status_code == 503
    assert "Traceback" not in response.text and "mcp" not in response.text.lower()
    record = last_run(engine)
    assert record.success == 0 and record.error_code == "mcp_unavailable"
