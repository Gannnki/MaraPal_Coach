import json

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from rag.knowledge import answer_knowledge, format_context, load_documents


def test_load_documents_preserves_evidence_and_citations(tmp_path):
    path = tmp_path / "knowledge.jsonl"
    path.write_text(json.dumps({
        "id": "nutrition/iron#lead", "text": "Iron matters.", "title": "Iron",
        "evidence": "moderate", "url": "https://running.wiki/nutrition/iron",
        "citations": [{"title": "Review", "resource": "https://example.test/paper"}],
    }) + "\n")
    documents = load_documents(path)
    assert documents[0].metadata["evidence"] == "moderate"
    context = format_context(documents)
    assert "Evidence: moderate" in context
    assert "https://example.test/paper" in context


class StaticRetriever:
    def __init__(self, documents):
        self.documents = documents

    def invoke(self, _question):
        return self.documents


def static_llm(answer):
    return RunnableLambda(lambda _prompt: AIMessage(content=answer))


def test_answer_sources_keep_numbers_and_primary_attribution():
    document = Document(
        id="concepts/lt#lead",
        page_content="Threshold is useful.",
        metadata={
            "chunk_id": "concepts/lt#lead", "title": "Lactate threshold",
            "section": "Training use", "url": "https://running.wiki/concepts/lt",
            "evidence": "moderate",
            "citations": json.dumps([
                {"title": "Faude et al.", "resource": "https://example.test/paper"}
            ]),
        },
    )
    answer, sources = answer_knowledge(
        "What is LT?", StaticRetriever([document]), static_llm("It is useful [1].")
    )

    assert answer == "It is useful [1]."
    assert sources[0]["number"] == 1
    assert sources[0]["chunk_id"] == "concepts/lt#lead"
    assert sources[0]["cited_in_answer"] is True
    assert sources[0]["primary_sources"][0]["resource"] == "https://example.test/paper"


def test_answer_rejects_citation_outside_retrieved_context():
    document = Document(page_content="Evidence", metadata={"title": "One"})
    with pytest.raises(ValueError, match=r"\[2\]"):
        answer_knowledge(
            "Question", StaticRetriever([document]), static_llm("Unsupported [2].")
        )
