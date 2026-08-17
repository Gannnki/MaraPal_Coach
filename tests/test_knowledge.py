import json

from rag.knowledge import format_context, load_documents


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
