"""Create/upgrade the database and load the synthetic data pack.

    uv run python -m support_copilot.db.seed

Safe to run repeatedly: fixture tables are emptied and reloaded in one
transaction, so the result is always the same rows and the same chunk IDs.
`assistant_runs` is left alone. Re-seeding resets `reviewed_at` to the fixture value.
"""

import json
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from support_copilot.config import BACKEND_DIR, DATA_DIR, db_url
from support_copilot.db.models import Article, ArticleChunk, Ticket, TicketMessage
from support_copilot.retrieval.chunking import build_index_text, chunk_article

log = logging.getLogger("support_copilot.seed")


def migrate() -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")


def _load(name: str, data_dir: Path) -> list[dict]:
    return json.loads((data_dir / name).read_text(encoding="utf-8"))


def seed(data_dir: Path = DATA_DIR) -> dict[str, int]:
    migrate()
    tickets = _load("tickets.json", data_dir)
    articles = _load("knowledge_articles.json", data_dir)

    engine = create_engine(db_url())
    counts = {"tickets": 0, "messages": 0, "articles": 0, "chunks": 0}
    with Session(engine) as session, session.begin():
        for table in ("tickets_fts", "ticket_messages", "tickets", "article_chunks", "articles"):
            session.execute(text(f"DELETE FROM {table}"))  # fixed table names, not user input

        for t in tickets:
            messages = t["messages"]
            session.add(
                Ticket(
                    **{k: v for k, v in t.items() if k != "messages"},
                    messages=[
                        TicketMessage(position=i, at=m["at"], author=m["author"], text=m["text"])
                        for i, m in enumerate(messages)
                    ],
                )
            )
            session.execute(
                text(
                    "INSERT INTO tickets_fts (ticket_id, title, description, messages, resolution_summary) "
                    "VALUES (:id, :title, :description, :messages, :resolution)"
                ),
                {
                    "id": t["id"],
                    "title": t["title"],
                    "description": t["description"],
                    "messages": "\n".join(m["text"] for m in messages),
                    "resolution": t["resolution_summary"] or "",
                },
            )
            counts["tickets"] += 1
            counts["messages"] += len(messages)

        for a in articles:
            session.add(Article(**a))
            for chunk in chunk_article(a["id"], a["body"]):
                session.add(
                    ArticleChunk(
                        id=chunk.id,
                        article_id=a["id"],
                        chunk_index=chunk.chunk_index,
                        title=a["title"],
                        category=a["category"],
                        text=chunk.text,
                        index_text=build_index_text(a["title"], a["tags"], chunk.text),
                    )
                )
                counts["chunks"] += 1
            counts["articles"] += 1
    engine.dispose()
    return counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log.info("Seeded %s", seed())
