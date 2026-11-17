"""TF-IDF index over knowledge chunks.

Built once in memory from the `article_chunks` table. A query is projected into
the same vector space and compared by cosine similarity.
"""

import math
from collections import Counter
from dataclasses import dataclass

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sqlalchemy import Connection, text

from support_copilot.retrieval.chunking import split_sentences
from support_copilot.schemas import KnowledgeHit, KnowledgeSearchResult, ScoredSentence

# Measured by `python -m support_copilot.eval`: the best wrong match scores 0.150.
# The weakest right ones are a paraphrase at 0.166 (refused) and T-104 at 0.197.
DEFAULT_THRESHOLD = 0.17
DEFAULT_TOP_K = 3
# A chunk of an article that already cleared the threshold is kept at this lower bar
# (same floor the composer uses for quotable sentences).
SIBLING_MIN_SCORE = 0.05

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
        self._analyze = self.vectorizer.build_analyzer()

    def search(
        self,
        query: str,
        category: str | None = None,
        top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> KnowledgeSearchResult:
        query_vec = self.vectorizer.transform([query]) * self._coverage(query)
        scores = (self.matrix @ query_vec.T).toarray().ravel()

        # Category filter first: an off-category chunk must never be returned,
        # however well it scores.
        candidates = [
            (float(scores[i]), chunk)
            for i, chunk in enumerate(self.chunks)
            if category is None or chunk.category == category
        ]
        candidates.sort(key=lambda pair: (-pair[0], pair[1].id))  # id breaks ties deterministically
        top_score = round(candidates[0][0], 4) if candidates else None

        # Articles are split into two-sentence chunks, so one procedure can span two
        # chunks: "account recovery after enabling MFA" matches KB-03's fallback step
        # (0.22) but not its main backup-code step (0.07). Once an article clears the
        # threshold, its other chunks need only share some query words to come along.
        accepted = {chunk.article_id for score, chunk in candidates if score >= threshold}
        candidates = [
            (score, chunk)
            for score, chunk in candidates
            if score >= threshold or (chunk.article_id in accepted and score >= SIBLING_MIN_SCORE)
        ]

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
        ]
        return KnowledgeSearchResult(hits=hits, threshold=threshold, top_score=top_score)

    def _coverage(self, query: str) -> float:
        """Share of the query's weight that the index knows, between 0 and 1.

        sklearn drops query words it has never seen, so "change the dashboard
        language to French" is scored as if the query were just "change" and
        matches KB-06 strongly. Here unseen words stay in the query's length.

        Each unseen word gets the smallest weight any indexed word has. That is
        deliberately mild: ticket text is full of ordinary words these few
        articles never use, and the heaviest weight (a word found in no chunk)
        pushed T-104's own draft below the threshold.
        """
        terms = Counter(self._analyze(query))
        vocabulary, idf = self.vectorizer.vocabulary_, self.vectorizer.idf_
        known_sq = sum(
            ((1 + math.log(tf)) * idf[vocabulary[t]]) ** 2 for t, tf in terms.items() if t in vocabulary
        )
        unseen_words = sum(1 for t in terms if t not in vocabulary and " " not in t)  # bigrams not counted twice
        total_sq = known_sq + unseen_words * float(idf.min()) ** 2
        return math.sqrt(known_sq / total_sq) if total_sq else 0.0

    def _score_sentences(self, query_vec, chunk_text: str) -> list[ScoredSentence]:
        """Score each whole sentence against the query so the composer can pick what to quote."""
        sentences = split_sentences(chunk_text)
        scores = (self.vectorizer.transform(sentences) @ query_vec.T).toarray().ravel()
        return [ScoredSentence(text=s, score=round(float(x), 4)) for s, x in zip(sentences, scores)]
