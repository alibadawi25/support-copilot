"""Initial schema: tickets, messages, articles, chunks, assistant runs, ticket FTS5 index.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("priority", sa.String(10), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("product_area", sa.String(40), nullable=False),
        sa.Column("created_at", sa.String(20), nullable=False),
        sa.Column("updated_at", sa.String(20), nullable=False),
        sa.Column("resolution_summary", sa.Text, nullable=True),
        sa.Column("reviewed_at", sa.String(20), nullable=True),
        sa.CheckConstraint("priority IN ('low','medium','high')", name="ck_tickets_priority"),
        sa.CheckConstraint("status IN ('open','resolved')", name="ck_tickets_status"),
    )
    op.create_index("ix_tickets_status_priority_category", "tickets", ["status", "priority", "category"])
    op.create_index("ix_tickets_category", "tickets", ["category"])

    op.create_table(
        "ticket_messages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ticket_id", sa.String(16), sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("at", sa.String(20), nullable=False),
        sa.Column("author", sa.String(20), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
    )
    op.create_index("ix_ticket_messages_ticket_position", "ticket_messages", ["ticket_id", "position"])

    op.create_table(
        "articles",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("tags", sa.JSON, nullable=False),
        sa.Column("applies_to", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(20), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
    )

    op.create_table(
        "article_chunks",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("article_id", sa.String(16), sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("index_text", sa.Text, nullable=False),
    )
    op.create_index("ix_article_chunks_article", "article_chunks", ["article_id"])
    op.create_index("ix_article_chunks_category", "article_chunks", ["category"])

    op.create_table(
        "assistant_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.String(20), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("ticket_id", sa.String(16), nullable=True),
        sa.Column("tools", sa.JSON, nullable=False),
        sa.Column("retrieval_method", sa.String(40), nullable=True),
        sa.Column("answer_state", sa.String(40), nullable=True),
        sa.Column("success", sa.Boolean, nullable=False),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=False),
    )
    op.create_index("ix_assistant_runs_created_at", "assistant_runs", ["created_at"])

    # Full-text index for similar-ticket search. SQLAlchemy has no FTS5 construct,
    # so it is raw SQL. It is filled by the seed script; ticket text never changes
    # afterwards (the only write is reviewed_at), so no sync triggers are needed.
    # porter = stemming, so "timed"/"timeout"/"times" style variants match better.
    op.execute(
        """
        CREATE VIRTUAL TABLE tickets_fts USING fts5(
            ticket_id UNINDEXED,
            title,
            description,
            messages,
            resolution_summary,
            tokenize = 'porter unicode61'
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tickets_fts")
    for table in ("assistant_runs", "article_chunks", "articles", "ticket_messages", "tickets"):
        op.drop_table(table)
