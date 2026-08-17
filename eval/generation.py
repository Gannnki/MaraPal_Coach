"""Prompt A/B evaluation with GPT generation and a Gemini DeepEval judge.

This is an explicit, paid offline experiment. It is intentionally not collected by
ordinary pytest. Retrieval is frozen once per question so only the prompt varies.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import time
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI

from rag.config import Settings
from rag.knowledge import generate_from_documents, load_documents, vector_store
from rag.retrieval import build_retriever
from rag.style import answer_instructions

PROMPTS = ("prompt_a", "prompt_b")
CITATION_RE = re.compile(r"\[(\d+)]")


def deterministic_checks(answer: str, context_count: int, disclaimer_required: bool) -> dict[str, bool]:
    citations = [int(number) for number in CITATION_RE.findall(answer)]
    lowered = answer.lower()
    return {
        "not_empty": bool(answer.strip()),
        "citations_valid": bool(citations) and all(1 <= number <= context_count for number in citations),
        "disclaimer_present": (
            not disclaimer_required
            or "not medical advice" in lowered
            or "非医疗建议" in answer
            or "不能替代医疗" in answer
            or "不构成医疗建议" in answer
        ),
    }


def build_metrics(judge: Any) -> dict[str, Any]:
    from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric, GEval
    from deepeval.test_case import SingleTurnParams

    common = {"model": judge, "threshold": 0.0, "async_mode": False}
    return {
        "faithfulness": FaithfulnessMetric(include_reason=True, **common),
        "answer_relevancy": AnswerRelevancyMetric(include_reason=True, **common),
        "evidence_fidelity": GEval(
            name="Evidence fidelity",
            evaluation_steps=[
                "Identify the evidence strength and uncertainty stated in the expected output and retrieval context.",
                "Assess whether the actual output expresses a matching degree of confidence.",
                "Penalize laundering limited, weak, or contested evidence into certainty.",
                "Do not reward verbosity or writing style; score only evidence fidelity.",
            ],
            evaluation_params=[
                SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.EXPECTED_OUTPUT,
                SingleTurnParams.RETRIEVAL_CONTEXT,
            ],
            **common,
        ),
        "completeness": GEval(
            name="Completeness",
            evaluation_steps=[
                "List the essential claims in the expected output.",
                "Check which essential claims are present in the actual output.",
                "Penalize material omissions but do not require identical wording or extra detail.",
            ],
            evaluation_params=[SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.EXPECTED_OUTPUT],
            **common,
        ),
        "style_alignment": GEval(
            name="Style alignment",
            evaluation_steps=[
                "Infer the user's formality and requested depth from the input.",
                "Assess whether the actual output matches that formality and depth without imitating mistakes or slang.",
                "For academic questions reward precision and explicit uncertainty; for casual questions reward natural accessible language.",
                "Do not score factual correctness in this metric.",
            ],
            evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
            **common,
        ),
    }


def score_case(
    metrics: dict[str, Any], test_case: Any, scores: dict[str, Any],
    checkpoint, *, retries: int = 3,
) -> dict[str, Any]:
    for name, metric in metrics.items():
        if name in scores:
            continue
        for attempt in range(1, retries + 1):
            try:
                metric.measure(test_case)
                scores[name] = {"score": metric.score, "reason": metric.reason}
                checkpoint()
                break
            except Exception:
                if attempt == retries:
                    raise
                delay = 10 * attempt
                print(f"  {name}: temporary failure; retrying in {delay}s", flush=True)
                time.sleep(delay)
    return scores


def summarize(cases: list[dict[str, Any]]) -> dict[str, Any]:
    metric_names = tuple(cases[0]["metrics"])
    summary = {
        name: round(statistics.mean(case["metrics"][name]["score"] for case in cases), 4)
        for name in metric_names
    }
    checks = [value for case in cases for value in case["checks"].values()]
    summary["deterministic_pass_rate"] = round(sum(checks) / len(checks), 4)
    summary["mean_generation_latency_ms"] = round(
        statistics.mean(case["generation_latency_ms"] for case in cases), 2
    )
    summary["questions"] = len(cases)
    return summary


def select_prompt(results: dict[str, Any]) -> str:
    """Trustworthiness first; relevance/style only break quality ties."""
    def key(prompt: str) -> tuple[float, ...]:
        item = results[prompt]["summary"]
        return (
            item["faithfulness"], item["evidence_fidelity"],
            item["deterministic_pass_rate"], item["answer_relevancy"],
            item["completeness"], item["style_alignment"],
            -item["mean_generation_latency_ms"],
        )
    return max(PROMPTS, key=key)


def write_results(path: Path, results: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("eval/generation_goldens.json"))
    parser.add_argument("--out", type=Path, default=Path("eval/results/generation.json"))
    parser.add_argument("--judge-model", default=os.getenv("MARAPAL_JUDGE_MODEL", "gemini-3.6-flash"))
    parser.add_argument("--limit", type=int, help="cheap smoke run on the first N goldens")
    parser.add_argument(
        "--no-resume", action="store_true",
        help="ignore a compatible checkpoint and rerun every generation/judgement",
    )
    parser.add_argument("--metric-retries", type=int, default=3)
    args = parser.parse_args()
    if not os.getenv("GOOGLE_API_KEY"):
        raise SystemExit("GOOGLE_API_KEY is required for the Gemini judge")

    from deepeval.models import GeminiModel
    from deepeval.test_case import LLMTestCase

    settings = Settings.from_env()
    goldens = json.loads(args.dataset.read_text(encoding="utf-8"))
    if args.limit:
        goldens = goldens[: args.limit]
    documents = load_documents(settings.knowledge_path)
    retriever = build_retriever(
        "vector", vector_store(settings), documents, k=settings.retrieval_k
    )

    
    generator = ChatOpenAI(model=settings.chat_model, temperature=0)
    judge = GeminiModel(model=args.judge_model, temperature=0)
    metrics = build_metrics(judge)
    experiment = {
        "generator": settings.chat_model, "judge": args.judge_model,
        "retrieval": "vector", "top_k": settings.retrieval_k,
    }
    results: dict[str, Any] = {"experiment": experiment}
    if args.out.exists() and not args.no_resume:
        saved = json.loads(args.out.read_text(encoding="utf-8"))
        if saved.get("experiment") == experiment:
            results = saved
    frozen_context = {
        golden["question"]: retriever.invoke(golden["question"])
        for golden in goldens
    }
    for prompt in PROMPTS:
        prompt_cases = results.get(prompt, {}).get("cases", [])
        by_question = {case["question"]: case for case in prompt_cases}
        for index, golden in enumerate(goldens, 1):
            existing = by_question.get(golden["question"])
            docs = frozen_context[golden["question"]]
            if existing:
                # Deterministic rules may evolve independently of paid judge scores.
                existing["checks"] = deterministic_checks(
                    existing["answer"], len(docs), golden["disclaimer_required"]
                )
            if existing and set(existing.get("metrics", {})) == set(metrics):
                print(f"[{prompt}] reusing checkpoint {index}/{len(goldens)}", flush=True)
                continue
            if existing:
                case_result = existing
                answer = case_result["answer"]
                print(f"[{prompt}] resuming metrics {index}/{len(goldens)}", flush=True)
            else:
                started = time.perf_counter()
                answer = generate_from_documents(
                    golden["question"], docs, generator,
                    answer_instructions=answer_instructions(golden["style"], golden["detail"]),
                    prompt_variant=prompt,
                )
                latency = (time.perf_counter() - started) * 1000
                case_result = {
                    "question": golden["question"], "answer": answer,
                    "metrics": {},
                    "checks": deterministic_checks(
                        answer, len(docs), golden["disclaimer_required"]
                    ),
                    "generation_latency_ms": round(latency, 2),
                }
                prompt_cases.append(case_result)
                by_question[golden["question"]] = case_result
                results[prompt] = {"cases": prompt_cases}
                write_results(args.out, results)
            test_case = LLMTestCase(
                input=golden["question"], actual_output=answer,
                expected_output=golden["expected_output"],
                retrieval_context=[doc.page_content for doc in docs],
            )
            print(f"[{prompt}] judging {index}/{len(goldens)}", flush=True)
            def checkpoint() -> None:
                results[prompt] = {"cases": prompt_cases}
                write_results(args.out, results)

            score_case(
                metrics, test_case, case_result["metrics"], checkpoint,
                retries=args.metric_retries,
            )
            results.pop("selected", None)
            results.pop("selection_rule", None)
            write_results(args.out, results)
        results[prompt] = {"summary": summarize(prompt_cases), "cases": prompt_cases}
        write_results(args.out, results)
    results["selected"] = select_prompt(results)
    results["selection_rule"] = (
        "Lexicographic: faithfulness, evidence fidelity, deterministic checks, "
        "answer relevancy, completeness, style alignment, then latency."
    )
    write_results(args.out, results)
    print(json.dumps({p: results[p]["summary"] for p in PROMPTS} | {"selected": results["selected"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
