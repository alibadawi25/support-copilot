"""Paths shared by the API, the MCP server and the seed script."""

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR.parent / "data" / "customer_support_data"


def db_path() -> Path:
    """SQLite file location. Read at call time so tests can point it at a temp file."""
    return Path(os.environ.get("SUPPORT_COPILOT_DB", BACKEND_DIR / "support_copilot.db"))


def db_url() -> str:
    return f"sqlite:///{db_path().as_posix()}"
