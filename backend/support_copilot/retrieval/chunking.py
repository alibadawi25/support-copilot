"""Split knowledge articles into small, citable chunks.

A chunk is a run of whole sentences. Sentences are never cut, because a
truncated sentence can lose the condition or negation that makes it true
("If the payment is pending, do not ask the customer to ...").
"""

import re
from dataclasses import dataclass

SENTENCES_PER_CHUNK = 2

# End of sentence = . ! or ? followed by whitespace and a capital letter or quote.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z'\"])")


@dataclass(frozen=True)
class Chunk:
    id: str  # stable: "<article_id>#chunk-<n>", n starts at 1
    article_id: str
    chunk_index: int
    text: str


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_BOUNDARY.split(text.strip()) if s.strip()]


def chunk_article(article_id: str, body: str, size: int = SENTENCES_PER_CHUNK) -> list[Chunk]:
    sentences = split_sentences(body)
    chunks = []
    for n, start in enumerate(range(0, len(sentences), size), start=1):
        chunks.append(
            Chunk(
                id=f"{article_id}#chunk-{n}",
                article_id=article_id,
                chunk_index=n,
                text=" ".join(sentences[start : start + size]),
            )
        )
    return chunks


def build_index_text(title: str, tags: list[str], chunk_text: str) -> str:
    """Text that is vectorised. Title and tags help recall; only `chunk_text` is ever quoted."""
    return f"{title}. {' '.join(tags)}. {chunk_text}"
