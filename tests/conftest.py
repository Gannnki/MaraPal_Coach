import pytest


@pytest.fixture(autouse=True)
def disable_langsmith_for_unit_tests(monkeypatch):
    """Keep ordinary pytest runs offline and out of the production trace project."""
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
