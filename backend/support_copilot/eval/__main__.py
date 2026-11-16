"""Print the retrieval evaluation report: `uv run python -m support_copilot.eval`."""

from sqlalchemy import create_engine

from support_copilot.config import db_url
from support_copilot.eval.dataset import QUERIES
from support_copilot.eval.retrieval_eval import (
    CORRECT,
    FALSE_ACCEPT,
    FALSE_REJECT,
    WRONG_SOURCE,
    Bm25Baseline,
    first_relevant_rank,
    ranking_metrics,
    sweep,
    tfidf_ranking,
)
from support_copilot.retrieval.tfidf import DEFAULT_THRESHOLD, KnowledgeIndex, load_chunks

THRESHOLDS = sorted({0.05, 0.10, 0.12, 0.15, 0.17, 0.20, 0.25, 0.30, DEFAULT_THRESHOLD})


def build_report() -> str:
    engine = create_engine(db_url())
    with engine.connect() as conn:
        chunks = load_chunks(conn)
    engine.dispose()
    index, bm25 = KnowledgeIndex(chunks), Bm25Baseline(chunks)
    answerable = [q for q in QUERIES if q.answerable]
    # Ranking ignores the category, so the same text asked in two scopes counts once.
    ranked_once = list({q.query: q for q in answerable}.values())
    articles = len({c.article_id for c in chunks})

    out = [
        "Retrieval evaluation",
        f"{len(QUERIES)} labelled queries ({len(answerable)} answerable, "
        f"{len(QUERIES) - len(answerable)} with no answer in the knowledge base); "
        f"{articles} articles, {len(chunks)} chunks.",
        "",
        f"1. Ranking, unscoped, {len(ranked_once)} distinct answerable queries",
        f"{'method':<14}{'hit@1':>7}{'hit@3':>7}{'MRR':>7}",
    ]
    rank_rows = []
    for q in ranked_once:
        rank_rows.append(
            (
                q,
                first_relevant_rank(tfidf_ranking(index, q.query), q.relevant),
                first_relevant_rank(bm25.ranking(q.query), q.relevant),
            )
        )
    for name, column in (("tfidf_cosine", 1), ("fts5_bm25", 2)):
        m = ranking_metrics([row[column] for row in rank_rows])
        out.append(f"{name:<14}{m.hit_at_1:>7.2f}{m.hit_at_3:>7.2f}{m.mrr:>7.2f}")

    out += ["", "Rank of the first relevant article per query (- = not retrieved)",
            f"{'query':<28}{'kind':<12}{'tfidf':>6}{'bm25':>6}"]
    for q, tfidf_rank, bm25_rank in rank_rows:
        out.append(f"{q.id:<28}{q.kind:<12}{tfidf_rank or '-':>6}{bm25_rank or '-':>6}")

    out += ["", "2. Threshold sweep, real path (query's own category scope + composer)",
            f"{'threshold':<11}{'correct':>8}{'false accept':>14}{'false reject':>14}{'wrong source':>14}"]
    table = sweep(index, QUERIES, THRESHOLDS)
    for t, row in table.items():
        mark = "  <- current" if t == DEFAULT_THRESHOLD else ""
        out.append(
            f"{t:<11.2f}{len(row[CORRECT]):>8}{len(row[FALSE_ACCEPT]):>14}"
            f"{len(row[FALSE_REJECT]):>14}{len(row[WRONG_SOURCE]):>14}{mark}"
        )

    current = table[DEFAULT_THRESHOLD]
    out += ["", f"Errors at the current threshold ({DEFAULT_THRESHOLD}):"]
    for label in (FALSE_ACCEPT, FALSE_REJECT, WRONG_SOURCE):
        out.append(f"  {label}: {', '.join(current[label]) or 'none'}")

    out += [
        "",
        "Read with care: seven articles and a hand-written query set. The numbers show",
        "where this index fails (paraphrases, very short queries); they do not predict",
        "accuracy on a real knowledge base.",
    ]
    return "\n".join(out)


if __name__ == "__main__":
    print(build_report())
