"""LangChain document loading, Chroma indexing, and evidence-aware RAG."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr

from .config import Settings

CORE_PROMPT = """You are MaraPal Coach, an evidence-aware running assistant by MaraPal. Answer only from
the supplied running.wiki context. If it is insufficient, say so. Preserve the
evidence grades: explicitly hedge limited, weak, or contested evidence. Cite factual
claims with the supplied source numbers, e.g. [1]. Do not recommend products or
invent citations. For health, injury, or nutrition questions, end with a brief
'Not medical advice' warning. Answer in the same language as the user's question.

Adapt presentation using this instruction, without changing facts, evidence standards,
citations, or safety rules:
{answer_instructions}"""

PROMPT_VARIANTS = {
    "prompt_a": CORE_PROMPT,
    "prompt_b": CORE_PROMPT
    + """

Organize the answer around these functions, adapting headings to the selected style
and omitting a section when it adds no value:
1. Give the direct answer first.
2. Explain the most relevant evidence and mechanisms.
3. State uncertainty, limitations, and practical caveats explicitly.
4. Keep citations immediately after the claims they support.
Do not repeat the same fact in multiple sections and do not add a separate bibliography.""",
}


def rag_prompt(variant: str = "prompt_a") -> ChatPromptTemplate:
    try:
        system = PROMPT_VARIANTS[variant]
    except KeyError:
        raise ValueError(f"unknown prompt variant: {variant}") from None
    return ChatPromptTemplate.from_messages(
        [("system", system), ("human", "Question: {question}\n\nContext:\n{context}")]
    )


def embeddings(
    settings: Settings, *, api_key: SecretStr | None = None
) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(model=settings.embedding_model, api_key=api_key)


def vector_store(
    settings: Settings, *, api_key: SecretStr | None = None
) -> Chroma:
    settings.chroma_path.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=settings.chroma_collection,
        embedding_function=embeddings(settings, api_key=api_key),
        persist_directory=str(settings.chroma_path),
        collection_metadata={"hnsw:space": "cosine"},
    )


def load_documents(path: Path) -> list[Document]:
    """Load wiki JSONL while converting Chroma metadata to scalar values."""
    documents: list[Document] = []
    seen: set[str] = set()
    try:
        stream = path.open(encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(f"knowledge file not found: {path}; run ingest/wiki.py") from None

    with stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            record_id, text = record.get("id"), record.get("text")
            if not isinstance(record_id, str) or not isinstance(text, str):
                raise ValueError(f"{path}:{line_number}: id and text must be strings")
            if record_id in seen:
                raise ValueError(f"{path}:{line_number}: duplicate id {record_id!r}")
            seen.add(record_id)
            metadata = {
                key: (json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value)
                for key, value in record.items()
                if key not in {"id", "text"} and value is not None
            }
            metadata["chunk_id"] = record_id
            documents.append(Document(page_content=text, metadata=metadata, id=record_id))
    return documents


def index_documents(store: Chroma, documents: Iterable[Document], batch_size: int = 64) -> int:
    docs = list(documents)
    for start in range(0, len(docs), batch_size):
        batch = docs[start : start + batch_size]
        store.add_documents(batch, ids=[str(doc.id) for doc in batch])
    return len(docs)


def _metadata_json(metadata: dict[str, Any], key: str) -> Any:
    value = metadata.get(key, "[]")
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return []


def format_context(documents: list[Document]) -> str:
    blocks = []
    for number, doc in enumerate(documents, 1):
        meta = doc.metadata
        citations = _metadata_json(meta, "citations")
        citation_text = "; ".join(
            f"{item.get('title', 'source')}: {item.get('resource') or item.get('wiki_url')}"
            for item in citations
        ) or meta.get("url", "running.wiki")
        blocks.append(
            f"[{number}] {meta.get('title', 'Untitled')}\n"
            f"Evidence: {meta.get('evidence', 'not graded')}\n"
            f"Page: {meta.get('url', '')}\nSources: {citation_text}\n"
            f"Content: {doc.page_content}"
        )
    return "\n\n".join(blocks)


def answer_knowledge(
    question: str, retriever: Any, llm: Any, answer_instructions: str = "",
    prompt_variant: str = "prompt_a",
) -> tuple[str, list[dict[str, Any]]]:
    documents = retriever.invoke(question)
    if not documents:
        return "I could not find relevant material in running.wiki.", []
    response = (rag_prompt(prompt_variant) | llm).invoke(
        {
            "question": question,
            "context": format_context(documents),
            "answer_instructions": answer_instructions,
        }
    )
    sources = [
        {
            "title": doc.metadata.get("title"),
            "url": doc.metadata.get("url"),
            "evidence": doc.metadata.get("evidence"),
        }
        for doc in documents
    ]
    return str(response.content), sources


def generate_from_documents(
    question: str, documents: list[Document], llm: Any, *,
    answer_instructions: str, prompt_variant: str,
) -> str:
    """Generate against frozen retrieval context for fair prompt experiments."""
    response = (rag_prompt(prompt_variant) | llm).invoke(
        {
            "question": question,
            "context": format_context(documents),
            "answer_instructions": answer_instructions,
        }
    )
    return str(response.content)
