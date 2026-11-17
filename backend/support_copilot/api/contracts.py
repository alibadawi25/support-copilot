"""REST request and response models. These are what `/docs` shows."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from support_copilot.schemas import Action, Answer, Category, TicketFilter, TicketMessageView

MAX_QUERY_CHARS = 500  # same bound the MCP tools enforce

TicketId = Annotated[str, Field(pattern=r"^T-\d{1,6}$", examples=["T-101"])]
Query = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUERY_CHARS)]

# Which request fields each action needs. Checked up front so a bad request is a 422.
_NEEDS_TICKET = {"summarize_ticket", "draft_reply"}


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Action
    ticket_id: TicketId | None = None
    query: Query | None = None
    category: Category | None = None
    filters: TicketFilter | None = None  # count_tickets only

    # Messages are shown to the agent as-is, so they say what to do, not which field failed.
    @model_validator(mode="after")
    def _required_fields(self) -> "AssistantRequest":
        if self.action in _NEEDS_TICKET and not self.ticket_id:
            raise ValueError("Select a ticket first.")
        if self.action == "search_knowledge" and not self.query:
            raise ValueError("Type a question to search the knowledge base.")
        if self.action == "similar_tickets" and not (self.ticket_id or self.query):
            raise ValueError("Select a ticket or describe the problem to find similar tickets.")
        if self.action == "count_tickets" and self.query:
            # Counting is filter-only; a question here would be silently ignored.
            raise ValueError("Count uses the filters and keyword, not a question.")
        if self.filters is not None and self.action != "count_tickets":
            raise ValueError("Filters apply only to Count.")
        return self


class ToolCall(BaseModel):
    tool: str
    arguments: dict
    ok: bool
    duration_ms: float


class RetrievalInfo(BaseModel):
    method: str
    top_k: int
    threshold: float | None = None  # knowledge search only
    top_score: float | None = None  # best score seen, even if below the threshold


class AssistantResponse(BaseModel):
    run_id: str
    answer: Answer
    retrieval: RetrievalInfo | None = None  # None for count_tickets (no retrieval)
    tool_trace: list[ToolCall]
    limitations: list[str]


class TicketSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    category: str
    priority: str
    status: str
    updated_at: str
    reviewed_at: str | None


class TicketDetail(TicketSummary):
    description: str
    product_area: str
    created_at: str
    resolution_summary: str | None
    messages: list[TicketMessageView]


class ReviewedUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewed: bool


class Health(BaseModel):
    status: str  # "ok" | "degraded"
    database: bool
    mcp_ready: bool
