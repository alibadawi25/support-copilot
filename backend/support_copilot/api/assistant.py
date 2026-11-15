"""One fixed flow per action: which MCP tools run, in what order, then the composer.

The action comes from a closed enum and picks a function below. Ticket and
article text only ever travels as tool arguments or quoted evidence, so nothing
a customer wrote can choose a tool or change a flow.
"""

from support_copilot.api.contracts import MAX_QUERY_CHARS, AssistantRequest, RetrievalInfo, ToolCall
from support_copilot.api.mcp_gateway import McpGateway
from support_copilot.composer import compose
from support_copilot.schemas import (
    Answer,
    KnowledgeSearchResult,
    SimilarTicketsResult,
    TicketCount,
    TicketFilter,
    TicketLookup,
    TicketView,
)

TOP_K = 3

Result = tuple[Answer, RetrievalInfo | None]


class TicketNotFound(Exception):
    pass


class _Flow:
    """Typed MCP calls for one request, all recorded in the same trace."""

    def __init__(self, gateway: McpGateway, trace: list[ToolCall]):
        self._gateway = gateway
        self._trace = trace

    async def call(self, tool: str, arguments: dict) -> dict:
        return await self._gateway.call(tool, arguments, self._trace)

    async def ticket(self, ticket_id: str) -> TicketView:
        data = await self.call("get_ticket", {"ticket_id": ticket_id})
        lookup = TicketLookup.model_validate(data)
        if not lookup.found or lookup.ticket is None:
            raise TicketNotFound(ticket_id)
        return lookup.ticket

    async def knowledge(self, query: str, category: str | None) -> tuple[KnowledgeSearchResult, RetrievalInfo]:
        data = await self.call("search_knowledge", {"query": query, "category": category, "top_k": TOP_K})
        result = KnowledgeSearchResult.model_validate(data)
        info = RetrievalInfo(
            method=result.method, top_k=TOP_K, threshold=result.threshold, top_score=result.top_score
        )
        return result, info


def _ticket_query(ticket: TicketView) -> str:
    return compose.ticket_query(ticket)[:MAX_QUERY_CHARS]


async def _search_knowledge(req: AssistantRequest, flow: _Flow) -> Result:
    result, info = await flow.knowledge(req.query, req.category)
    return compose.compose_search_knowledge(result), info


async def _summarize_ticket(req: AssistantRequest, flow: _Flow) -> Result:
    ticket = await flow.ticket(req.ticket_id)
    result, info = await flow.knowledge(_ticket_query(ticket), ticket.category)
    return compose.compose_summarize_ticket(ticket, result), info


async def _draft_reply(req: AssistantRequest, flow: _Flow) -> Result:
    ticket = await flow.ticket(req.ticket_id)
    result, info = await flow.knowledge(req.query or _ticket_query(ticket), ticket.category)
    return compose.compose_draft_reply(ticket, result), info


async def _similar_tickets(req: AssistantRequest, flow: _Flow) -> Result:
    query = req.query
    if req.ticket_id:
        ticket = await flow.ticket(req.ticket_id)
        query = query or _ticket_query(ticket)
    data = await flow.call(
        "search_resolved_tickets",
        {"query": query, "exclude_ticket_id": req.ticket_id, "category": req.category, "limit": TOP_K},
    )
    result = SimilarTicketsResult.model_validate(data)
    return compose.compose_similar_tickets(result.tickets), RetrievalInfo(method=result.method, top_k=TOP_K)


async def _count_tickets(req: AssistantRequest, flow: _Flow) -> Result:
    filters = req.filters or TicketFilter()
    data = await flow.call("count_tickets", filters.model_dump())
    return compose.compose_count_tickets(filters, TicketCount.model_validate(data)), None


_FLOWS = {
    "search_knowledge": _search_knowledge,
    "summarize_ticket": _summarize_ticket,
    "draft_reply": _draft_reply,
    "similar_tickets": _similar_tickets,
    "count_tickets": _count_tickets,
}

_LIMITATIONS = {
    "search_knowledge": "Knowledge search is lexical (TF-IDF): synonyms and paraphrases can be missed.",
    "summarize_ticket": "Knowledge search is lexical (TF-IDF): synonyms and paraphrases can be missed.",
    "draft_reply": "Draft only: nothing is sent to the customer. Review and edit before use.",
    "similar_tickets": "Similar-ticket search is keyword-based (FTS5 bm25) over resolved tickets only.",
    "count_tickets": "Counts reflect the local database at the time of the call.",
}


def limitations(action: str) -> list[str]:
    return [
        "Answers are assembled from verbatim source sentences; no language model is involved.",
        _LIMITATIONS[action],
    ]


async def run_action(req: AssistantRequest, gateway: McpGateway, trace: list[ToolCall]) -> Result:
    return await _FLOWS[req.action](req, _Flow(gateway, trace))
