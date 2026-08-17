from app.api import AskRequest, SlidingWindowRateLimiter, create_app, openai_http_error
from rag.config import Settings
from fastapi.testclient import TestClient


class FakeGraph:
    def invoke(self, state, config=None):
        return {
            "answer": "Grounded answer", "route": "knowledge", "sources": [],
            "answer_style": "neutral", "answer_detail": "standard",
        }


def test_api_routes_and_request_validation():
    app = create_app(settings=Settings(), graph_factory=lambda *args, **kwargs: FakeGraph())
    paths = {route.path for route in app.routes}
    assert {
        "/health", "/api/v1/ask", "/api/v1/validate-key", "/api/v1/feedback",
        "/api/v1/monitoring", "/monitoring", "/docs",
    } <= paths
    request = AskRequest(question="What is LT1?")
    assert request.question == "What is LT1?"


def test_ask_requires_user_api_key(tmp_path):
    settings = Settings(monitoring_db=tmp_path / "monitoring.sqlite3")
    app = create_app(settings=settings, graph_factory=lambda *args, **kwargs: FakeGraph())

    with TestClient(app) as client:
        response = client.post("/api/v1/ask", json={"question": "What is LT1?"})

    assert response.status_code == 401
    assert response.json()["detail"] == "An OpenAI API key is required."


def test_ask_passes_secret_to_graph_factory_without_tracing_it(tmp_path):
    captured = {}

    def graph_factory(*args, **kwargs):
        captured.update(kwargs)
        return FakeGraph()

    settings = Settings(monitoring_db=tmp_path / "monitoring.sqlite3")
    app = create_app(settings=settings, graph_factory=graph_factory)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ask",
            json={"question": "What is LT1?"},
            headers={"X-OpenAI-API-Key": "sk-test-secret"},
        )

    assert response.status_code == 200
    assert captured["api_key"].get_secret_value() == "sk-test-secret"


def test_validate_key_accepts_valid_key_without_exposing_it(tmp_path):
    seen = []
    settings = Settings(monitoring_db=tmp_path / "monitoring.sqlite3")
    app = create_app(settings=settings, key_validator=lambda key: seen.append(key) or True)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/validate-key",
            headers={"X-OpenAI-API-Key": "sk-test-secret"},
        )

    assert response.status_code == 200
    assert response.json() == {"valid": True}
    assert seen == ["sk-test-secret"]
    assert "sk-test-secret" not in response.text


def test_validate_key_rejects_invalid_key(tmp_path):
    settings = Settings(monitoring_db=tmp_path / "monitoring.sqlite3")
    app = create_app(settings=settings, key_validator=lambda key: False)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/validate-key",
            headers={"X-OpenAI-API-Key": "invalid"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "The OpenAI API key is invalid or revoked."


def test_openai_errors_are_safely_mapped():
    cases = [
        ("AuthenticationError", 401),
        ("PermissionDeniedError", 403),
        ("RateLimitError", 429),
        ("APIConnectionError", 503),
        ("APITimeoutError", 503),
        ("InternalServerError", 503),
        ("UnknownProviderError", 500),
    ]

    for error_name, expected_status in cases:
        secret = "sk-secret-must-not-leak"
        error = type(error_name, (Exception,), {})(secret)
        result = openai_http_error(error)
        assert result.status_code == expected_status
        assert secret not in result.detail


def test_feedback_rejects_zero_rating(tmp_path):
    settings = Settings(monitoring_db=tmp_path / "monitoring.sqlite3")
    app = create_app(settings=settings, graph_factory=lambda *args, **kwargs: FakeGraph())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/feedback",
            json={
                "interaction_id": "00000000-0000-0000-0000-000000000001",
                "rating": 0,
            },
        )

    assert response.status_code == 422


def test_ask_rate_limit_is_ten_requests_per_minute(tmp_path):
    settings = Settings(monitoring_db=tmp_path / "monitoring.sqlite3")
    app = create_app(
        settings=settings,
        graph_factory=lambda *args, **kwargs: FakeGraph(),
        ask_rate_limiter=SlidingWindowRateLimiter(limit=10, window_seconds=60),
    )
    headers = {
        "X-OpenAI-API-Key": "sk-test-secret",
        "X-MaraPal-Visitor-ID": "visitor-one",
    }

    with TestClient(app) as client:
        responses = [
            client.post(
                "/api/v1/ask", json={"question": "What is LT1?"}, headers=headers,
            )
            for _ in range(11)
        ]

    assert all(response.status_code == 200 for response in responses[:10])
    assert responses[10].status_code == 429
    assert responses[10].headers["retry-after"]
    assert responses[10].json()["detail"] == (
        "Too many MaraPal questions. Please wait before asking again."
    )
