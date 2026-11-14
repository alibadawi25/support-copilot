"""TF-IDF index over knowledge chunks.

Built once in memory from the `article_chunks` table. A query is projected into
the same vector space and compared by cosine similarity.
"""

from dataclasses import dataclass

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sqlalchemy import Connection, text

from support_copilot.retrieval.chunking import split_sentences
from support_copilot.schemas import KnowledgeHit, KnowledgeSearchResult, ScoredSentence

DEFAULT_THRESHOLD = 0.15
DEFAULT_TOP_K = 3

# sklearn's English list drops negations. We keep them so "do not ask" and
# "not a completed charge" stay distinguishable as bigrams.
_NEGATIONS = {"no", "not", "nor", "never", "cannot", "without"}
STOP_WORDS = frozenset(ENGLISH_STOP_WORDS - _NEGATIONS)


@dataclass(frozen=True)
class ChunkRecord:
    id: str
    article_id: str
    title: str
    category: str
    text: str  # quoted as evidence
    index_text: str  # vectorised (title + tags + text)


def load_chunks(conn: Connection) -> list[ChunkRecord]:
    rows = conn.execute(
        text("SELECT id, article_id, title, category, text, index_text FROM article_chunks ORDER BY id")
    )
    return [ChunkRecord(*row) for row in rows]


class KnowledgeIndex:
    def __init__(self, chunks: list[ChunkRecord]):
        self.chunks = chunks
        # Unigrams + bigrams; sublinear TF so a repeated word (title + tag + body)
        # does not dominate. Rows are L2-normalised, so a dot product is the cosine.
        self.vectorizer = TfidfVectorizer(
            stop_words=list(STOP_WORDS), ngram_range=(1, 2), sublinear_tf=True
        )
        self.matrix = self.vectorizer.fit_transform(c.index_text for c in chunks)

    def search(
        self,
        query: str,
        category: str | None = None,
        top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> KnowledgeSearchResult:
        query_vec = self.vectorizer.transform([query])
        scores = (self.matrix @ query_vec.T).toarray().ravel()

        # Category filter first: an off-category chunk must never be returned,
        # however well it scores.
        candidates = [
            (float(scores[i]), chunk)
            for i, chunk in enumerate(self.chunks)
            if category is None or chunk.category == category
        ]
        candidates.sort(key=lambda pair: (-pair[0], pair[1].id))  # id breaks ties deterministically

        hits = [
            KnowledgeHit(
                chunk_id=chunk.id,
                article_id=chunk.article_id,
                title=chunk.title,
                category=chunk.category,
                excerpt=chunk.text,
                score=round(score, 4),
                sentences=self._score_sentences(query_vec, chunk.text),
            )
            for score, chunk in candidates[:top_k]
            if score >= threshold
        ]
        return KnowledgeSearchResult(
            hits=hits,
            threshold=threshold,
            top_score=round(candidates[0][0], 4) if candidates else None,
        )

    def _score_sentences(self, query_vec, chunk_text: str) -> list[ScoredSentence]:
        """Score each whole sentence against the query so the composer can pick what to quote."""
        sentences = split_sentences(chunk_text)
        scores = (self.vectorizer.transform(sentences) @ query_vec.T).toarray().ravel()
        return [ScoredSentence(text=s, score=round(float(x), 4)) for s, x in zip(sentences, scores)]
