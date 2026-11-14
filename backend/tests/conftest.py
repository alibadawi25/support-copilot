import pytest
from sqlalchemy import create_engine

from support_copilot.config import db_url
from support_copilot.db.seed import seed


@pytest.fixture(scope="session")
def seeded_db(tmp_path_factory):
    """A freshly migrated and seeded SQLite file, shared by the whole test session."""
    path = tmp_path_factory.mktemp("db") / "test.db"
    mp = pytest.MonkeyPatch()
    mp.setenv("SUPPORT_COPILOT_DB", str(path))
    seed()
    yield path
    mp.undo()


@pytest.fixture
def engine(seeded_db):
    engine = create_engine(db_url())
    yield engine
    engine.dispose()
