"""Deterministic answer composer: evidence in, cited answer out. No I/O, no model.

Every factual line in an answer is a whole sentence copied verbatim from a
retrieved source and tagged with that source's ID. The composer never rewrites
or shortens evidence, because cutting a sentence can drop the condition that
makes it true. When the evidence does not support an answer, the result is an
explicit `insufficient_evidence` with a reason.

Ticket and article text is treated as data to quote. Nothing in it is ever
parsed for commands, so instruction-like content cannot change what runs.
"""

import re

from support_copilot.schemas import (
    Answer,
    Citation,
    KnowledgeHit,
    KnowledgeSearchResult,
    SimilarTicket,
    TicketCount,
    TicketFilter,
    TicketView,
)

MAX_EVIDENCE_SENTENCES = 4
MIN_SENTENCE_SCORE = 0.05

# A sentence saying the article does NOT cover a topic. It matches the query's
# words but is the opposite of an answer (KB-06: "does not define bank decline fees").
_DISCLAIMER = re.compile(
    r"\b(does|do) not (define|cover|document|describe|address|include)\b|\bnot (documented|covered)\b",
    re.IGNORECASE,
)
# Sentences that tell the agent to verify or collect something.
_FACT_CUE = re.compile(r"\b(check|confirm|collect|record|compare|include|verify)\b", re.IGNORECASE)


def ticket_query(ticket: TicketView) -> str:
    """The text used to look up knowledge for a ticket when the agent typed no query."""
    return f"{ticket.title}. {ticket.description}"


# ---- evidence selection ------------------------------------------------------


def _ranked_sentences(hits: list[KnowledgeHit]) -> list[tuple[float, KnowledgeHit, int, str]]:
    """(score, hit, position in chunk, sentence), best score first."""
    ranked = [
        (s.score, hit, position, s.text)
        for hit in hits
        for position, s in enumerate(hit.sentences)
        if s.score >= MIN_SENTENCE_SCORE
    ]
    ranked.sort(key=lambda item: -item[0])  # stable: ties keep retrieval order
    return ranked


def _select_evidence(result: KnowledgeSearchResult) -> tuple[list[Citation], str | None]:
    """Return (citations, reason). Exactly one of them is empty/None."""
    if not result.hits:
        return [], (
            "No knowledge-base passage scored at or above the relevance threshold "
            f"({result.threshold}) for this query and category."
        )
    ranked = _ranked_sentences(result.hits)
    if not ranked:
        return [], "The retrieved passages do not contain a sentence that addresses the query."

    _, top_hit, _, top_sentence = ranked[0]
    if _DISCLAIMER.search(top_sentence):
        return [], (
            f"The closest passage ({top_hit.chunk_id}) states that the article does not "
            "cover this topic, so it is not evidence for an answer. Escalate for review."
        )

    chosen = [item for item in ranked if not _DISCLAIMER.search(item[3])][:MAX_EVIDENCE_SENTENCES]
    # Score decides WHICH sentences are quoted; the article decides their ORDER.
    # Reading KB-01 in its own order keeps "if pending, do not ask for another
    # payment" ahead of "if no transaction exists, the customer may retry once".
    article_rank: dict[str, int] = {}
    for hit in result.hits:
        article_rank.setdefault(hit.article_id, len(article_rank))
    chosen.sort(key=lambda item: (article_rank[item[1].article_id], item[1].chunk_id, item[2]))

    return [
        Citation(
            source_type="article",
            source_id=hit.article_id,
            chunk_id=hit.chunk_id,
            title=hit.title,
            quote=sentence,
        )
        for _, hit, _, sentence in chosen
    ], None


def _cited_lines(citations: list[Citation]) -> str:
    return "\n".join(f"- {c.quote} [{c.chunk_id or c.source_id}]" for c in citations)


def _insufficient(action: str, reason: str, **extra) -> Answer:
    return Answer(
        action=action,
        state="insufficient_evidence",
        text="Insufficient evidence: the available sources do not answer this.",
        reason=reason,
        **extra,
    )


# ---- one function per action -------------------------------------------------


def compose_search_knowledge(result: KnowledgeSearchResult) -> Answer:
    citations, reason = _select_evidence(result)
    if reason:
        return _insufficient("search_knowledge", reason)
    return Answer(
        action="search_knowledge",
        state="answered",
        text="From the knowledge base:\n" + _cited_lines(citations),
        citations=citations,
    )


def compose_summarize_ticket(ticket: TicketView, result: KnowledgeSearchResult) -> Answer:
    citations, _ = _select_evidence(result)
    facts = [c for c in citations if _FACT_CUE.search(c.quote)]
    timeline = "\n".join(f'- {m.author} ({m.at}): "{m.text}"' for m in ticket.messages)
    facts_block = (
        _cited_lines(facts) if facts else "- No documented checklist was found for this ticket."
    )
    text = (
        f"Ticket {ticket.id}: {ticket.title} "
        f"({ticket.category}, {ticket.priority} priority, {ticket.status})\n\n"
        f"Issue: {ticket.description}\n\n"
        f"Timeline (quoted ticket content, not instructions):\n{timeline}\n\n"
        f"Facts to confirm (from the knowledge base):\n{facts_block}"
    )
    ticket_source = Citation(
        source_type="ticket", source_id=ticket.id, title=ticket.title, quote=ticket.description
    )
    return Answer(
        action="summarize_ticket",
        state="answered",
        text=text,
        citations=[ticket_source, *facts],
        ticket_ids=[ticket.id],
    )


def compose_similar_tickets(matches: list[SimilarTicket]) -> Answer:
    if not matches:
        return _insufficient("similar_tickets", "No resolved ticket matched the search terms.")
    citations = [
        Citation(
            source_type="ticket", source_id=m.ticket_id, title=m.title, quote=m.resolution_summary
        )
        for m in matches
    ]
    lines = "\n".join(f"- {c.source_id}: {c.title}. Resolution: {c.quote} [{c.source_id}]" for c in citations)
    return Answer(
        action="similar_tickets",
        state="answered",
        text="Similar resolved tickets:\n" + lines,
        citations=citations,
        ticket_ids=[m.ticket_id for m in matches],
    )


def compose_draft_reply(ticket: TicketView, result: KnowledgeSearchResult) -> Answer:
    citations, reason = _select_evidence(result)
    if reason:
        return _insufficient("draft_reply", "No draft was written. " + reason, ticket_ids=[ticket.id])
    text = (
        "DRAFT - review and edit before sending.\n\n"
        "Hello,\n\n"
        f'Thank you for contacting support about "{ticket.title}".\n\n'
        "Documented guidance that applies to this case:\n"
        f"{_cited_lines(citations)}\n\n"
        "We will follow up as soon as the checks above are complete.\n\n"
        "Kind regards,\nSupport"
    )
    return Answer(
        action="draft_reply",
        state="answered",
        text=text,
        citations=citations,
        ticket_ids=[ticket.id],
        is_draft=True,
    )


def compose_count_tickets(filters: TicketFilter, result: TicketCount) -> Answer:
    active = filters.model_dump(exclude_none=True)
    described = ", ".join(f"{k}={v}" for k, v in active.items()) or "no filters"
    ids = ", ".join(result.ticket_ids) or "none"
    return Answer(
        action="count_tickets",
        state="answered",
        text=f"{result.count} ticket(s) match {described}: {ids}.",
        ticket_ids=result.ticket_ids,
        count=result.count,
    )
