from app.monitoring_page import render_dashboard


def test_monitoring_page_has_six_charts():
    report = {
        "totals": {"requests": 1, "responses": 1, "positive_rate": 100.0,
                   "avg_latency_ms": 125.0},
        "requests_by_day": [], "routes": [], "styles": [],
        "latency_by_route": [], "ratings": [], "statuses": [],
    }
    page = render_dashboard(report)
    assert "MaraPal Coach Monitoring" in page
    assert page.count('class="chart"') == 6
