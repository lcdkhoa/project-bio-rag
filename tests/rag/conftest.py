import pytest


@pytest.fixture(autouse=True)
def _isolate_dotenv(monkeypatch):
    """Keep src.config reloads from re-reading a developer's real .env.

    python-dotenv's load_dotenv() (called at the top of src/config.py) uses
    find_dotenv(), which walks UP the directory tree from src/config.py's
    location looking for the nearest ".env" file. When this worktree lives
    nested under the main repo checkout, that walk can find the main repo's
    real, gitignored ".env" (e.g. one with a local-path EMBEDDING_MODEL
    override for offline use). A test that does
    `monkeypatch.delenv(...); importlib.reload(src.config)` to assert coded
    defaults would otherwise have those vars silently repopulated by that
    outer .env, defeating the isolation the test is trying to establish.

    Scoped to tests/rag only, and auto-reverted by monkeypatch after each
    test, so it has no effect outside this test package.
    """
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
