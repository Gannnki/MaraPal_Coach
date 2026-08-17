from rag.config import Settings


def test_dotenv_values_are_available(monkeypatch):
    monkeypatch.setenv("MARAPAL_RETRIEVAL_MODE", "bm25")
    assert Settings.from_env().retrieval_mode == "bm25"
