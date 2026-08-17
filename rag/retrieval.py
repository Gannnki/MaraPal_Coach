"""Vector and hybrid retrievers with reciprocal-rank fusion."""

from __future__ import annotations

import re
from typing import Any

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, Field
from rank_bm25 import BM25Okapi

TOKEN_RE = re.compile(r"(?u)\b\w\w+\b")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


class HybridRetriever(BaseRetriever):
    """Fuse semantic Chroma results with exact-term BM25 results."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    vector_retriever: Any
    documents: list[Document]
    k: int = 5
    fetch_k: int = 15
    rrf_constant: int = 60
    bm25: Any = Field(default=None, exclude=True)

    def model_post_init(self, __context: Any) -> None:
        self.bm25 = BM25Okapi([tokenize(doc.page_content) for doc in self.documents])

    @staticmethod
    def identity(document: Document) -> str:
        return str(document.metadata.get("chunk_id") or document.id or document.page_content)

    def _get_relevant_documents(self, query: str, *, run_manager: Any) -> list[Document]:
        vector_docs = self.vector_retriever.invoke(query)
        lexical_scores = self.bm25.get_scores(tokenize(query))
        lexical_indexes = sorted(
            range(len(self.documents)), key=lambda index: lexical_scores[index], reverse=True
        )[: self.fetch_k]
        lexical_docs = [self.documents[index] for index in lexical_indexes]

        scores: dict[str, float] = {}
        documents: dict[str, Document] = {}
        for result in (vector_docs, lexical_docs):
            for rank, document in enumerate(result, 1):
                key = self.identity(document)
                documents[key] = document
                scores[key] = scores.get(key, 0.0) + 1 / (self.rrf_constant + rank)
        ranked = sorted(scores, key=scores.get, reverse=True)
        return [documents[key] for key in ranked[: self.k]]


class BM25Retriever(BaseRetriever):
    """Pure lexical baseline over the same processed knowledge chunks."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    documents: list[Document]
    k: int = 5
    bm25: Any = Field(default=None, exclude=True)

    def model_post_init(self, __context: Any) -> None:
        self.bm25 = BM25Okapi([tokenize(doc.page_content) for doc in self.documents])

    def _get_relevant_documents(self, query: str, *, run_manager: Any) -> list[Document]:
        scores = self.bm25.get_scores(tokenize(query))
        indexes = sorted(range(len(self.documents)), key=lambda i: scores[i], reverse=True)
        return [self.documents[index] for index in indexes[: self.k]]


def build_retriever(
    mode: str, store: Any, documents: list[Document], *, k: int = 5,
) -> BaseRetriever:
    vector = store.as_retriever(search_kwargs={"k": max(k * 3, 10) if mode == "hybrid" else k})
    if mode == "vector":
        return vector
    if mode == "bm25":
        return BM25Retriever(documents=documents, k=k)
    if mode == "hybrid":
        return HybridRetriever(
            vector_retriever=vector, documents=documents, k=k, fetch_k=max(k * 3, 10)
        )
    raise ValueError("retrieval mode must be bm25, vector, or hybrid")
