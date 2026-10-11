"""Shared fixtures. Every test runs against a throwaway database in mock-LLM mode and never
reads the developer's .env, so results are the same on a laptop and in CI."""

import os

# Must happen before app.config is imported anywhere: Settings reads ENV_FILE at import time.
os.environ["ENV_FILE"] = os.devnull

import pytest  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import init_db, reset_engine  # noqa: E402


def _refresh() -> None:
    get_settings.cache_clear()
    reset_engine()


@pytest.fixture(scope="session", autouse=True)
def isolated_settings(tmp_path_factory):
    patch = pytest.MonkeyPatch()
    db_dir = tmp_path_factory.mktemp("db")
    patch.setenv("DB_URL", f"sqlite:///{db_dir / 'session.db'}")
    patch.setenv("MOCK_LLM", "true")
    _refresh()
    yield
    patch.undo()
    _refresh()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """An empty database of its own, for tests that write."""
    monkeypatch.setenv("DB_URL", f"sqlite:///{tmp_path / 'fresh.db'}")
    _refresh()
    init_db()
    yield
    _refresh()
