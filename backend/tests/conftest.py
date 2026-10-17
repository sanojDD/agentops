import pytest

from app.graph import nodes
from app.retrieval.store import get_store


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    get_store().clear()
    monkeypatch.setattr(nodes, "RETRY_DELAY_SECONDS", 0)
    yield
    get_store().clear()
