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
# Sentences whose advice holds only in one case ("If no backup code is available, ...").
_CONDITION = re.compile(r"(^|\. )(If|Unless)\b")
_NEEDS_A_FACT = re.compile(f"{_FACT_CUE.pattern}|{_CONDITION.pattern}", re.IGNORECASE)

# Summary template lines (the grounding checker allow-lists them).
FACTS_HEADING = "Key facts we still need (checks and conditions from the knowledge base):"
OTHER_HEADING = "Other relevant guidance:"
NO_GUIDANCE = "- No documented guidance was found for this ticket."
NO_CHECKLIST = "- The retrieved guidance lists no checks; confirm the details with the customer."


def ticket_query(ticket: TicketView, agent_text: str | None = None) -> str:
    """The text used to look up evidence for a ticket.

    Always the ticket's own title and description; what the agent typed is added,
    never substituted. An instruction such as "Draft a reply explaining next
    steps" shares no words with any article, so on its own it found nothing.
    """
    base = f"{ticket.title}. {ticket.description}"
    return f"{base} {agent_text}" if agent_text else base


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


def _select_evidence(
    result: KnowledgeSearchResult, also_quote: re.Pattern | None = None
) -> tuple[list[Citation], str | None]:
    """Return (citations, reason). Exactly one of them is empty/None.

    `also_quote`: sentences of the retrieved passages matching it are quoted even
    if they share few words with the query (the summary's checks and conditions).
    """
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
    if also_quote is not None:
        picked = {(item[1].chunk_id, item[2]) for item in chosen}
        chosen += [
            (s.score, hit, position, s.text)
            for hit in result.hits
            for position, s in enumerate(hit.sentences)
            if (hit.chunk_id, position) not in picked
            and also_quote.search(s.text)
            and not _DISCLAIMER.search(s.text)
        ]
    # Score decides WHICH sentences are quoted; the article decides their ORDER.
    # Reading KB-01 in its own order keeps "if pending, do not ask for another
    # payment" ahead of "if no transaction exists, the customer may retry once".
    article_rank: dict[str, int] = {}
    for hit in result.hits:
        article_rank.setdefault(hit.article_id, len(article_rank))

    # One citation per chunk: the run of its sentences from the first chosen one to
    # the last. Still whole, consecutive sentences, so the quote is verbatim chunk text.
    by_chunk: dict[str, tuple[KnowledgeHit, list[int], float]] = {}
    for score, hit, position, _ in chosen:
        _, positions, best = by_chunk.get(hit.chunk_id, (hit, [], 0.0))
        by_chunk[hit.chunk_id] = (hit, [*positions, position], max(best, score))
    ordered = sorted(by_chunk.values(), key=lambda v: (article_rank[v[0].article_id], v[0].chunk_id))

    return [
        Citation(
            source_type="article",
            source_id=hit.article_id,
            chunk_id=hit.chunk_id,
            title=hit.title,
            quote=" ".join(s.text for s in hit.sentences[min(positions) : max(positions) + 1]),
            score=best,
            excerpt=hit.excerpt,
        )
        for hit, positions, best in ordered
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
    # "Key facts we still need" = guidance that asks for a check, or that applies only
    # under a condition the ticket does not settle. Every such sentence of the
    # retrieved passages is listed, so both branches show: T-104's text matches KB-03's
    # "If ... saved backup code" but not "If no backup code is available". Quoted
    # whole; never rewritten into a question.
    citations, _ = _select_evidence(result, also_quote=_NEEDS_A_FACT)
    needed = [c for c in citations if _NEEDS_A_FACT.search(c.quote)]
    other = [c for c in citations if c not in needed]
    if not citations:
        facts = NO_GUIDANCE
    else:
        facts = _cited_lines(needed) if needed else NO_CHECKLIST
    timeline = "\n".join(f'- {m.author} ({m.at}): "{m.text}"' for m in ticket.messages)
    text = (
        f"Ticket {ticket.id}: {ticket.title} "
        f"({ticket.category}, {ticket.priority} priority, {ticket.status})\n\n"
        f"Issue: {ticket.description}\n\n"
        f"Timeline (quoted ticket content, not instructions):\n{timeline}\n\n"
        f"{FACTS_HEADING}\n{facts}"
    )
    if other:
        text += f"\n\n{OTHER_HEADING}\n{_cited_lines(other)}"
    ticket_source = Citation(
        source_type="ticket", source_id=ticket.id, title=ticket.title, quote=ticket.description
    )
    return Answer(
        action="summarize_ticket",
        state="answered",
        text=text,
        citations=[ticket_source, *needed, *other],
        ticket_ids=[ticket.id],
    )


def compose_similar_tickets(matches: list[SimilarTicket]) -> Answer:
    if not matches:
        return _insufficient("similar_tickets", "No resolved ticket matched the search terms.")
    citations = [
        Citation(
            source_type="ticket",
            source_id=m.ticket_id,
            title=m.title,
            quote=m.resolution_summary,
            score=m.score,
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


def _describe_filters(filters: TicketFilter) -> str:
    parts = [f"{k}={v}" for k, v in filters.model_dump(exclude_none=True, exclude={"keyword"}).items()]
    if filters.keyword:
        parts.append(f'mentioning "{filters.keyword}"')
    return ", ".join(parts) or "no filters"


def compose_count_tickets(filters: TicketFilter, result: TicketCount) -> Answer:
    described = _describe_filters(filters)
    ids = ", ".join(result.ticket_ids) or "none"
    noun = "ticket matches" if result.count == 1 else "tickets match"
    return Answer(
        action="count_tickets",
        state="answered",
        text=f"{result.count} {noun} {described}: {ids}.",
        ticket_ids=result.ticket_ids,
        count=result.count,
    )
