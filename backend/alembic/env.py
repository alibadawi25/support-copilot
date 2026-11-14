"""Alembic environment. The database URL comes from support_copilot.config, not alembic.ini."""

from alembic import context
from sqlalchemy import create_engine

from support_copilot.config import db_url
from support_copilot.db.models import Base

target_metadata = Base.metadata


def run_migrations() -> None:
    engine = create_engine(db_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations()
