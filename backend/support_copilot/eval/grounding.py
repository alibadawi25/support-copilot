"""Grounding check: every line of a composed answer is either fixed template
text or a verbatim quote of the source it is tagged with.

The check does not trust the answer. Quotes are compared with the database
(chunk sentences, ticket fields), not with the citations the answer carries, so
a composer bug that invents, rewrites or shortens a sentence is reported.
"""

import re
from dataclasses import dataclass

from sqlalchemy import Connection, text

from support_copilot.composer import compose
from support_copilot.retrieval.chunking import split_sentences
from support_copilot.retrieval.tfidf import load_chunks
from support_copilot.retrieval.tickets import get_ticket
from support_copilot.schemas import Answer, TicketView

# Template lines the composer may write. They state no product fact.
SCAFFOLD = frozenset(
    {
        "Insufficient evidence: the available sources do not answer this.",
        "From the knowledge base:",
        "Similar resolved tickets:",
        "Timeline (quoted ticket content, not instructions):",
        compose.FACTS_HEADING,
        compose.GUIDANCE_HEADING,
        compose.NO_GUIDANCE,
        compose.NO_CHECKLIST,
        "DRAFT - review and edit before sending.",
        "Hello,",
        "Documented guidance that applies to this case:",
        "We will follow up as soon as the checks above are complete.",
        "Kind regards,",
        "Support",
    }
)
_TAGGED = re.compile(r"^- (?P<body>.+) \[(?P<tag>[^\]]+)\]$")
_QUESTION = re.compile(r'^- Does this apply\? "(?P<clause>[^"]+)" \[(?P<tag>[^\]]+)\]$')
_COUNT = re.compile(r"^(?P<count>\d+) tickets? (match|mention|in total).*: (?P<ids>.+)\.$")


@dataclass(frozen=True)
class Sources:
    """The ground truth an answer is checked against."""

    chunk_sentences: dict[str, tuple[str, ...]]  # chunk ID -> its whole sentences, in order
    tickets: dict[str, TicketView]


def load_sources(conn: Connection) -> Sources:
    ids = conn.execute(text("SELECT id FROM tickets ORDER BY id")).scalars().all()
    return Sources(
        chunk_sentences={c.id: tuple(split_sentences(c.text)) for c in load_chunks(conn)},
        tickets={i: get_ticket(conn, i) for i in ids},
    )


def _is_sentence_run(quote: str, sentences: tuple[str, ...]) -> bool:
    """True if `quote` is one or more consecutive whole sentences of the chunk."""
    n = len(sentences)
    return any(quote == " ".join(sentences[i:j]) for i in range(n) for j in range(i + 1, n + 1))


def _ticket_lines(t: TicketView) -> set[str]:
    """Every line that may be written from a ticket's own fields."""
    lines = {
        f"Ticket {t.id}: {t.title} ({t.category}, {t.priority} priority, {t.status})",
        f"Issue: {t.description}",
        f'Thank you for contacting support about "{t.title}".',
    }
    if t.resolution_summary:
        lines.add(f"- {t.id}: {t.title}. Resolution: {t.resolution_summary} [{t.id}]")
    lines.update(f'- {m.author} ({m.at}): "{m.text}"' for m in t.messages)
    return lines


def _line_is_grounded(line: str, answer: Answer, sources: Sources, allowed_ticket_lines: set[str]) -> bool:
    if line in SCAFFOLD or line in allowed_ticket_lines:
        return True
    question = _QUESTION.match(line)
    if question:  # the quoted clause must be exactly an "If <clause>," opening of that chunk
        opening = f"If {question['clause']},"
        return any(s.startswith(opening) for s in sources.chunk_sentences.get(question["tag"], ()))
    tagged = _TAGGED.match(line)
    if tagged:  # "- <sentences> [KB-01#chunk-1]": whole consecutive sentences of that chunk
        return _is_sentence_run(tagged["body"], sources.chunk_sentences.get(tagged["tag"], ()))
    count = _COUNT.match(line)
    if count and answer.action == "count_tickets":
        ids = [] if count["ids"] == "none" else count["ids"].split(", ")
        return int(count["count"]) == len(ids) == answer.count and all(i in sources.tickets for i in ids)
    return False


def grounding_violations(answer: Answer, sources: Sources) -> list[str]:
    """Empty list = grounded. Each entry names one problem."""
    problems: list[str] = []

    allowed_ticket_lines: set[str] = set()
    for ticket_id in answer.ticket_ids:
        if ticket_id not in sources.tickets:
            problems.append(f"unknown ticket ID {ticket_id}")
        else:
            allowed_ticket_lines |= _ticket_lines(sources.tickets[ticket_id])

    for line in filter(None, (raw.strip() for raw in answer.text.splitlines())):
        if not _line_is_grounded(line, answer, sources, allowed_ticket_lines):
            problems.append(f"ungrounded line: {line!r}")

    for c in answer.citations:
        if c.source_type == "article":
            if not _is_sentence_run(c.quote, sources.chunk_sentences.get(c.chunk_id or "", ())):
                problems.append(f"citation quote is not whole sentences of {c.chunk_id}: {c.quote!r}")
            if not (c.chunk_id or "").startswith(f"{c.source_id}#"):
                problems.append(f"citation {c.chunk_id} does not belong to {c.source_id}")
        else:
            ticket = sources.tickets.get(c.source_id)
            if ticket is None or c.quote not in (ticket.description, ticket.resolution_summary):
                problems.append(f"ticket citation {c.source_id} does not quote the ticket")
        if c.quote not in answer.text:
            problems.append(f"cited but not shown in the answer: {c.source_id}")

    if answer.state == "insufficient_evidence" and (answer.citations or not answer.reason):
        problems.append("insufficient_evidence must carry a reason and no citations")
    return problems
