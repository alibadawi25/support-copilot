"""SQLAlchemy models.

Timestamps are ISO-8601 UTC strings (e.g. 2026-11-12T09:15:00Z). SQLite has no
native datetime type, and this format sorts chronologically as plain text.
"""

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40))
    priority: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10))
    product_area: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[str] = mapped_column(String(20))
    updated_at: Mapped[str] = mapped_column(String(20))
    resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[str | None] = mapped_column(String(20), nullable=True)

    messages: Mapped[list["TicketMessage"]] = relationship(
        back_populates="ticket", order_by="TicketMessage.position", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # The queue filters and count_tickets both filter on these three together.
        Index("ix_tickets_status_priority_category", "status", "priority", "category"),
        Index("ix_tickets_category", "category"),
    )


class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)  # order within the timeline
    at: Mapped[str] = mapped_column(String(20))
    author: Mapped[str] = mapped_column(String(20))  # "customer" | "agent"
    text: Mapped[str] = mapped_column(Text)

    ticket: Mapped[Ticket] = relationship(back_populates="messages")

    __table_args__ = (Index("ix_ticket_messages_ticket_position", "ticket_id", "position"),)


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(40))
    tags: Mapped[list[str]] = mapped_column(JSON)
    applies_to: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(20))
    body: Mapped[str] = mapped_column(Text)

    chunks: Mapped[list["ArticleChunk"]] = relationship(
        back_populates="article", order_by="ArticleChunk.chunk_index", cascade="all, delete-orphan"
    )


class ArticleChunk(Base):
    """One retrievable unit. `text` is what gets quoted; `index_text` is what gets vectorised."""

    __tablename__ = "article_chunks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # e.g. KB-03#chunk-1
    article_id: Mapped[str] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(40))
    text: Mapped[str] = mapped_column(Text)
    index_text: Mapped[str] = mapped_column(Text)

    article: Mapped[Article] = relationship(back_populates="chunks")

    __table_args__ = (
        Index("ix_article_chunks_article", "article_id"),
        Index("ix_article_chunks_category", "category"),
    )


class AssistantRun(Base):
    """Metadata about one assistant action. Deliberately holds no ticket or query text."""

    __tablename__ = "assistant_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # uuid4
    created_at: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(40))
    ticket_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    tools: Mapped[list[str]] = mapped_column(JSON)
    retrieval_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    answer_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer)

    __table_args__ = (Index("ix_assistant_runs_created_at", "created_at"),)
