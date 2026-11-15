import json
import os
import sys

import pytest
from mcp import Client, StdioServerParameters
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from support_copilot.config import BACKEND_DIR
from support_copilot.mcp_server.readonly import open_readonly_engine
from support_copilot.mcp_server.server import build_server


@pytest.fixture
def server(seeded_db):
    return build_server(seeded_db)


async def test_lists_four_tools_and_two_resource_templates(server):
    async with Client(server) as client:
        tools = {t.name for t in (await client.list_tools()).tools}
        templates = {t.uri_template for t in (await client.list_resource_templates()).resource_templates}
    assert tools == {"get_ticket", "search_knowledge", "search_resolved_tickets", "count_tickets"}
    assert templates == {"support://tickets/{ticket_id}", "support://knowledge/{article_id}"}


async def test_every_tool_is_advertised_as_read_only(server):
    async with Client(server) as client:
        tools = (await client.list_tools()).tools
    for tool in tools:
        assert tool.annotations.read_only_hint is True, tool.name
        assert tool.annotations.destructive_hint is False, tool.name


async def test_get_ticket_returns_structured_ticket_and_typed_not_found(server):
    async with Client(server) as client:
        hit = await client.call_tool("get_ticket", {"ticket_id": "T-101"})
        miss = await client.call_tool("get_ticket", {"ticket_id": "T-999"})
    assert not hit.is_error
    assert hit.structured_content["found"] is True
    assert hit.structured_content["ticket"]["id"] == "T-101"
    assert hit.structured_content["ticket"]["messages"]
    assert not miss.is_error
    assert miss.structured_content == {"found": False, "ticket": None}


async def test_search_knowledge_returns_scored_hits_with_metadata(server):
    async with Client(server) as client:
        result = await client.call_tool(
            "search_knowledge", {"query": "reset MFA authenticator", "category": "account_access"}
        )
    data = result.structured_content
    assert data["method"] == "tfidf_cosine"
    assert data["hits"] and all(h["score"] >= data["threshold"] for h in data["hits"])
    assert all(h["category"] == "account_access" for h in data["hits"])


async def test_count_and_similar_tools(server):
    async with Client(server) as client:
        count = await client.call_tool("count_tickets", {"status": "open"})
        similar = await client.call_tool(
            "search_resolved_tickets", {"query": "payment pending duplicate charge", "exclude_ticket_id": "T-101"}
        )
    assert count.structured_content["count"] == len(count.structured_content["ticket_ids"]) > 0
    assert similar.structured_content["method"] == "fts5_bm25"
    assert "T-101" not in [t["ticket_id"] for t in similar.structured_content["tickets"]]


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("search_knowledge", {"query": ""}),
        ("search_knowledge", {"query": "x" * 501}),
        ("search_knowledge", {"query": "refund", "top_k": 50}),
        ("search_knowledge", {"query": "refund", "category": "not_a_category"}),
        ("get_ticket", {"ticket_id": "T-1'; DROP TABLE tickets;--"}),
        ("count_tickets", {"status": "open OR 1=1"}),
    ],
)
async def test_out_of_bounds_arguments_are_tool_errors(server, tool, args):
    async with Client(server) as client:
        result = await client.call_tool(tool, args)
    assert result.is_error


async def test_resources_return_ticket_and_article_json(server):
    async with Client(server) as client:
        ticket = json.loads((await client.read_resource("support://tickets/T-101")).contents[0].text)
        article = json.loads((await client.read_resource("support://knowledge/KB-01")).contents[0].text)
        with pytest.raises(Exception):
            await client.read_resource("support://tickets/T-999")
    assert ticket["id"] == "T-101"
    assert article["id"] == "KB-01" and article["body"] and isinstance(article["tags"], list)


def test_server_connection_cannot_write(seeded_db):
    engine = open_readonly_engine(seeded_db)
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA query_only")).scalar() == 1
        for statement in (
            "UPDATE tickets SET status = 'resolved'",
            "DELETE FROM tickets",
            "CREATE TABLE evil (x)",
        ):
            with pytest.raises(OperationalError):
                conn.execute(text(statement))


def test_readonly_engine_does_not_create_a_missing_database(tmp_path):
    missing = tmp_path / "nope.db"
    with pytest.raises(OperationalError):
        open_readonly_engine(missing).connect()
    assert not missing.exists()


async def test_stdio_round_trip_in_a_separate_process(seeded_db):
    """The real transport: spawn the server as its own process and talk over stdio."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "support_copilot.mcp_server"],
        cwd=str(BACKEND_DIR),
        env={**os.environ, "SUPPORT_COPILOT_DB": str(seeded_db)},
    )
    async with Client(params) as client:
        assert len((await client.list_tools()).tools) == 4
        result = await client.call_tool("count_tickets", {})
        assert result.structured_content["count"] > 0
        resource = await client.read_resource("support://knowledge/KB-01")
        assert json.loads(resource.contents[0].text)["id"] == "KB-01"
