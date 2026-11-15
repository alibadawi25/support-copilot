"""The only database handle the MCP server ever gets: a read-only one."""

import sqlite3
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import NullPool


def open_readonly_engine(path: Path) -> Engine:
    """Engine whose connections cannot write, enforced at two independent layers.

    1. `mode=ro` in the file URI: SQLite opens the file read-only (and refuses
       to create it if it is missing).
    2. `PRAGMA query_only = ON`: the connection rejects any statement that would
       change the database, even if layer 1 were ever misconfigured.
    """
    uri = f"{path.resolve().as_uri()}?mode=ro"  # as_uri() percent-encodes spaces

    def connect() -> sqlite3.Connection:
        # The SDK may run sync tools in a worker thread; each call opens its own
        # connection (NullPool), so sharing across threads is not a concern.
        raw = sqlite3.connect(uri, uri=True, check_same_thread=False)
        raw.execute("PRAGMA query_only = ON")
        return raw

    return create_engine("sqlite://", creator=connect, poolclass=NullPool)
