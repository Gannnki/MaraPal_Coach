from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from rag.retrieval import BM25Retriever, HybridRetriever, tokenize


class StaticRetriever(BaseRetriever):
    documents: list[Document]

    def _get_relevant_documents(self, query, *, run_manager):
        return self.documents


def test_tokenize_is_case_insensitive():
    assert tokenize("LT1 and LACTATE") == ["lt1", "and", "lactate"]


def test_hybrid_adds_exact_keyword_result():
    lexical = Document(page_content="The LT1 threshold is aerobic.", metadata={"chunk_id": "lt1"})
    semantic = Document(page_content="General running advice.", metadata={"chunk_id": "general"})
    retriever = HybridRetriever(
        vector_retriever=StaticRetriever(documents=[semantic]),
        documents=[lexical, semantic], k=2, fetch_k=2,
    )
    ids = [doc.metadata["chunk_id"] for doc in retriever.invoke("LT1")]
    assert "lt1" in ids


def test_bm25_ranks_exact_keyword_first():
    docs = [
        Document(page_content="General running advice."),
        Document(page_content="LT1 is the first lactate threshold."),
        Document(page_content="Marathon taper and recovery."),
    ]
    assert BM25Retriever(documents=docs, k=1).invoke("LT1")[0] == docs[1]
