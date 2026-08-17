from rag.monitoring import dashboard, initialize, record_interaction, save_feedback


def test_feedback_is_upserted_and_dashboard_has_six_series(tmp_path):
    path = tmp_path / "monitoring.sqlite3"
    initialize(path)
    record_interaction(
        path, interaction_id="interaction-1", trace_id="00000000-0000-0000-0000-000000000001",
        question="Question", latency_ms=125.0, status="success", route="knowledge",
        answer_style="casual", answer_detail="brief",
    )
    save_feedback(path, interaction_id="interaction-1", rating=-1)
    save_feedback(path, interaction_id="interaction-1", rating=1)

    report = dashboard(path)
    assert report["totals"]["responses"] == 1
    assert report["ratings"] == [{"rating": "positive", "responses": 1}]
    assert {
        "requests_by_day", "routes", "styles", "latency_by_route", "ratings", "statuses"
    } <= report.keys()
