"""Compare BM25, vector, and hybrid retrieval against labelled questions."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from rag.config import Settings
from rag.knowledge import load_documents, vector_store
from rag.retrieval import build_retriever


def evaluate(retriever, cases: list[dict], k: int) -> dict:
    reciprocal_ranks, hits, latencies = [], [], []
    for case in cases:
        started = time.perf_counter()
        documents = retriever.invoke(case["question"])
        latencies.append((time.perf_counter() - started) * 1000)
        pages = [doc.metadata.get("page") for doc in documents[:k]]
        ranks = [index + 1 for index, page in enumerate(pages) if page in case["relevant_pages"]]
        hits.append(bool(ranks))
        reciprocal_ranks.append(1 / min(ranks) if ranks else 0)
    return {
        f"hit@{k}": sum(hits) / len(hits),
        f"mrr@{k}": sum(reciprocal_ranks) / len(reciprocal_ranks),
        "mean_latency_ms": round(statistics.mean(latencies), 2),
        "questions": len(cases),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("eval/retrieval_questions.json"))
    parser.add_argument("--out", type=Path, default=Path("eval/results/retrieval.json"))
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    settings = Settings.from_env()
    cases = json.loads(args.dataset.read_text(encoding="utf-8"))
    docs, store = load_documents(settings.knowledge_path), vector_store(settings)
    results: dict = {
        mode: evaluate(build_retriever(mode, store, docs, k=args.k), cases, args.k)
        for mode in ("bm25", "vector", "hybrid")
    }
    metric = f"mrr@{args.k}"
    methods = ("bm25", "vector", "hybrid")
    results["selected"] = max(
        methods,
        key=lambda mode: (results[mode][metric], results[mode][f"hit@{args.k}"], -results[mode]["mean_latency_ms"]),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
