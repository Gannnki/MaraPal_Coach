from eval.generation import deterministic_checks, select_prompt


def test_deterministic_checks_validate_citations_and_disclaimer():
    checks = deterministic_checks("Claim [1]. Not medical advice.", 2, True)
    assert all(checks.values())
    assert deterministic_checks("结论 [1]。不构成医疗建议。", 2, True)["disclaimer_present"]
    assert not deterministic_checks("Claim [3].", 2, False)["citations_valid"]


def test_prompt_selection_prioritizes_faithfulness():
    results = {
        "prompt_a": {"summary": {"faithfulness": .9, "evidence_fidelity": .8, "deterministic_pass_rate": 1, "answer_relevancy": .8, "completeness": .8, "style_alignment": .7, "mean_generation_latency_ms": 500}},
        "prompt_b": {"summary": {"faithfulness": .8, "evidence_fidelity": 1, "deterministic_pass_rate": 1, "answer_relevancy": 1, "completeness": 1, "style_alignment": 1, "mean_generation_latency_ms": 100}},
    }
    assert select_prompt(results) == "prompt_a"
