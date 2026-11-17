"""The eval harness itself, plus the retrieval outcomes it pins at the shipped threshold."""

import pytest

from support_copilot.eval.__main__ import build_report
from support_copilot.eval.dataset import QUERIES
from support_copilot.eval.retrieval_eval import (
    FALSE_ACCEPT,
    FALSE_REJECT,
    WRONG_SOURCE,
    Bm25Baseline,
    first_relevant_rank,
    ranking_metrics,
    sweep,
    tfidf_ranking,
)
from support_copilot.retrieval.tfidf import DEFAULT_THRESHOLD


def test_first_relevant_rank():
    assert first_relevant_rank(["KB-05", "KB-03"], frozenset({"KB-03"})) == 2
    assert first_relevant_rank(["KB-05"], frozenset({"KB-03"})) is None


def test_ranking_metrics_on_known_ranks():
    m = ranking_metrics([1, 2, None, 4])
    assert (m.hit_at_1, m.hit_at_3) == (0.25, 0.5)
    assert m.mrr == pytest.approx((1 + 1 / 2 + 1 / 4) / 4)


def test_both_rankers_put_the_export_article_first(index):
    query = "CSV export with more than 50,000 rows times out; use a background job"
    assert tfidf_ranking(index, query)[0] == "KB-04"
    assert Bm25Baseline(index.chunks).ranking(query)[0] == "KB-04"


def test_bm25_baseline_survives_fts_syntax(index):
    assert Bm25Baseline(index.chunks).ranking('"export" AND NEAR(^csv* -job') != []
    assert Bm25Baseline(index.chunks).ranking("?? -- !!") == []


def test_outcomes_at_the_shipped_threshold(index):
    """Pins what the README reports. A change here means retrieval behaviour changed."""
    row = sweep(index, QUERIES, [DEFAULT_THRESHOLD])[DEFAULT_THRESHOLD]
    expected_ids = {q.id for q in QUERIES if q.kind == "expected"}
    errors = set(row[FALSE_ACCEPT] + row[FALSE_REJECT] + row[WRONG_SOURCE])

    assert not errors & expected_ids  # the supplied cases are all right
    assert row[WRONG_SOURCE] == []  # never answers from an off-topic article
    # Known lexical false accepts: the article shares the topic words ("account email
    # address", "export the report") but not the asked-for thing. They score 0.25+,
    # above any threshold that keeps T-104 (0.197), so no threshold fixes them.
    assert row[FALSE_ACCEPT] == ["change_email", "pdf_export"]
    # Sparse retrieval misses paraphrases and two-word queries; it refuses rather than guesses.
    assert row[FALSE_REJECT] == [
        "mfa_short_unscoped", "mfa_short_scoped", "mfa_paraphrase", "charged_twice", "bill_changed", "big_download",
        "database_password", "one_time_code",
    ]


def test_report_builds_from_the_seeded_database(seeded_db):
    report = build_report()
    assert "hit@1" in report and "<- current" in report and "fts5_bm25" in report
