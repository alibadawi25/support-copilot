"""Typed contracts shared by retrieval, the composer, the MCP server and the API."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

Status = Literal["open", "resolved"]
Priority = Literal["low", "medium", "high"]
Category = Literal[
    "checkout", "account_access", "billing", "exports", "notifications", "integrations", "security"
]
Action = Literal[
    "search_knowledge", "summarize_ticket", "similar_tickets", "draft_reply", "count_tickets"
]
AnswerState = Literal["answered", "insufficient_evidence"]


# ---- retrieval results -------------------------------------------------------


class ScoredSentence(BaseModel):
    text: str  # one whole sentence, never truncated
    score: float  # cosine similarity to the query


class KnowledgeHit(BaseModel):
    chunk_id: str
    article_id: str
    title: str
    category: str
    excerpt: str  # the chunk's own sentences (no title/tags)
    score: float
    sentences: list[ScoredSentence]


class KnowledgeSearchResult(BaseModel):
    # Chunks at or above the threshold, plus other chunks of an accepted article; best first.
    hits: list[KnowledgeHit]
    threshold: float
    top_score: float | None  # best score seen after the category filter, even if rejected
    method: str = "tfidf_cosine"


class SimilarTicket(BaseModel):
    ticket_id: str
    title: str
    category: str
    resolution_summary: str
    score: float  # higher is better (negated bm25)


class SimilarTicketsResult(BaseModel):
    tickets: list[SimilarTicket]  # resolved tickets only, best first
    method: str = "fts5_bm25"


MAX_KEYWORD_CHARS = 100
Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_KEYWORD_CHARS)]


class TicketFilter(BaseModel):
    """Allowed count filters. Field filters are enums bound as parameters; the keyword
    reaches SQL only as an FTS5 MATCH expression of quoted words (`build_fts_query`)."""

    model_config = ConfigDict(extra="forbid")  # an unknown filter is an error, not ignored

    status: Status | None = None
    priority: Priority | None = None
    category: Category | None = None
    keyword: Keyword | None = None  # every word must appear in the ticket text


class TicketCount(BaseModel):
    count: int
    ticket_ids: list[str]


class TicketMessageView(BaseModel):
    at: str
    author: str
    text: str


class TicketView(BaseModel):
    id: str
    title: str
    description: str
    category: str
    priority: str
    status: str
    messages: list[TicketMessageView]
    resolution_summary: str | None = None


class TicketLookup(BaseModel):
    """get_ticket result. An unknown ID is a normal outcome, not a tool failure."""

    found: bool
    ticket: TicketView | None = None


class ArticleView(BaseModel):
    id: str
    title: str
    category: str
    tags: list[str]
    updated_at: str
    body: str


# ---- composer output ---------------------------------------------------------


class Citation(BaseModel):
    source_type: Literal["article", "ticket"]
    source_id: str  # KB-03 or T-105
    chunk_id: str | None = None  # KB-03#chunk-1 for articles
    title: str
    quote: str  # verbatim: whole consecutive sentences of one chunk, or a ticket field
    score: float | None = None  # best sentence score in the quote (None for the ticket itself)
    excerpt: str | None = None  # the whole chunk the quote came from, for context in the UI


class Answer(BaseModel):
    action: Action
    state: AnswerState
    text: str
    reason: str | None = None  # set when state is insufficient_evidence
    citations: list[Citation] = []
    ticket_ids: list[str] = []
    count: int | None = None
    is_draft: bool = False
