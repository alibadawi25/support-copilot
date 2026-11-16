"""Retrieval metrics: ranking quality (hit@k, MRR) and the threshold sweep.

Ranking is measured unscoped (no category filter) on answerable queries, because
with one or two articles per category a scoped ranking is trivially right.
The sweep runs the real path (search with the query's own scope, then the
composer) and counts wrong outcomes at each threshold.
"""

import sqlite3
from dataclasses import dataclass

from support_copilot.composer.compose import compose_search_knowledge
from support_copilot.eval.dataset import EvalQuery
from support_copilot.retrieval.tfidf import ChunkRecord, KnowledgeIndex
from support_copilot.retrieval.tickets import build_fts_query

# ---- two rankers with the same signature: query -> article IDs, best first ----


def tfidf_ranking(index: KnowledgeIndex, query: str) -> list[str]:
    result = index.search(query, top_k=len(index.chunks), threshold=0.0)
    return _unique(h.article_id for h in result.hits if h.score > 0)


class Bm25Baseline:
    """FTS5 bm25 over the same chunk text the TF-IDF index sees. Eval only."""

    def __init__(self, chunks: list[ChunkRecord]):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE VIRTUAL TABLE chunks USING fts5(article_id UNINDEXED, body)")
        self.db.executemany(
            "INSERT INTO chunks VALUES (?, ?)", [(c.article_id, c.index_text) for c in chunks]
        )

    def ranking(self, query: str) -> list[str]:
        match = build_fts_query(query)
        if match is None:
            return []
        rows = self.db.execute(
            "SELECT article_id FROM chunks WHERE chunks MATCH ? ORDER BY bm25(chunks), rowid",
            (match,),
        )
        return _unique(r[0] for r in rows)


def _unique(items) -> list[str]:
    return list(dict.fromkeys(items))  # keeps first (best) position of each article


# ---- ranking metrics ---------------------------------------------------------


def first_relevant_rank(ranking: list[str], relevant: frozenset[str]) -> int | None:
    """1-based position of the first relevant article, or None if it was not retrieved."""
    for position, article_id in enumerate(ranking, start=1):
        if article_id in relevant:
            return position
    return None


@dataclass(frozen=True)
class RankingMetrics:
    queries: int
    hit_at_1: float
    hit_at_3: float
    mrr: float


def ranking_metrics(ranks: list[int | None]) -> RankingMetrics:
    n = len(ranks)
    return RankingMetrics(
        queries=n,
        hit_at_1=sum(r == 1 for r in ranks) / n,
        hit_at_3=sum(r is not None and r <= 3 for r in ranks) / n,
        mrr=sum(1 / r for r in ranks if r) / n,
    )


# ---- threshold sweep ---------------------------------------------------------

# Outcome of one query at one threshold.
CORRECT = "correct"
FALSE_ACCEPT = "false_accept"  # answered a question the knowledge base cannot answer
FALSE_REJECT = "false_reject"  # refused a question it can answer
WRONG_SOURCE = "wrong_source"  # answered, but cited only articles that are not relevant


def outcome(index: KnowledgeIndex, q: EvalQuery, threshold: float) -> str:
    answer = compose_search_knowledge(index.search(q.query, category=q.category, threshold=threshold))
    answered = answer.state == "answered"
    if not q.answerable:
        return FALSE_ACCEPT if answered else CORRECT
    if not answered:
        return FALSE_REJECT
    cited = {c.source_id for c in answer.citations}
    return CORRECT if cited & q.relevant else WRONG_SOURCE


def sweep(index: KnowledgeIndex, queries: list[EvalQuery], thresholds: list[float]) -> dict[float, dict[str, list[str]]]:
    """threshold -> outcome -> IDs of the queries with that outcome."""
    table: dict[float, dict[str, list[str]]] = {}
    for t in thresholds:
        row: dict[str, list[str]] = {CORRECT: [], FALSE_ACCEPT: [], FALSE_REJECT: [], WRONG_SOURCE: []}
        for q in queries:
            row[outcome(index, q, t)].append(q.id)
        table[t] = row
    return table
