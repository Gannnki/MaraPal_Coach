from __future__ import annotations

from collections import deque
from contextlib import asynccontextmanager
import logging
import math
from threading import Lock
import time
from typing import Any, Callable, Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, SecretStr
import requests

from rag.config import Settings
from rag.graph import build_graph
from rag.monitoring import (
    dashboard, initialize, record_interaction, save_feedback,
    sync_langsmith_feedback,
)
from app.monitoring_page import render_dashboard

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """Small in-memory limiter suitable for the single-process MVP API."""

    def __init__(
        self, limit: int = 10, window_seconds: int = 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.clock = clock
        self.requests: dict[str, deque[float]] = {}
        self.lock = Lock()

    def check(self, visitor_id: str) -> tuple[bool, int]:
        now = self.clock()
        cutoff = now - self.window_seconds
        with self.lock:
            timestamps = self.requests.setdefault(visitor_id, deque())
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= self.limit:
                retry_after = max(
                    1, math.ceil(self.window_seconds - (now - timestamps[0]))
                )
                return False, retry_after
            timestamps.append(now)
            return True, 0


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


class Source(BaseModel):
    title: str | None = None
    url: str | None = None
    evidence: str | None = None


class AskResponse(BaseModel):
    answer: str
    route: str
    retrieval_mode: str
    answer_style: str
    answer_detail: str
    interaction_id: UUID
    trace_id: UUID
    sources: list[Source] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    interaction_id: UUID
    rating: Literal[-1, 1]
    comment: str | None = Field(default=None, max_length=1000)


class FeedbackResponse(BaseModel):
    saved: bool
    langsmith_synced: bool


class KeyValidationResponse(BaseModel):
    valid: bool


def validate_openai_api_key(api_key: str) -> bool:
    """Check authentication without running a model or creating a trace."""
    try:
        response = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            503, "OpenAI key validation is temporarily unavailable."
        ) from exc
    if response.status_code == 200:
        return True
    if response.status_code == 401:
        return False
    if response.status_code == 403:
        raise HTTPException(
            403, "The OpenAI API key does not have the required permission."
        )
    raise HTTPException(
        503, "OpenAI key validation is temporarily unavailable."
    )


def openai_http_error(exc: Exception) -> HTTPException:
    """Translate provider failures without exposing raw exception content."""
    error_name = type(exc).__name__
    status_code = getattr(exc, "status_code", None)
    if error_name == "AuthenticationError" or status_code == 401:
        return HTTPException(
            401, "OpenAI rejected the API key. Save a valid key and try again."
        )
    if error_name == "PermissionDeniedError" or status_code == 403:
        return HTTPException(
            403, "This API key does not have permission for the required OpenAI model."
        )
    if error_name == "RateLimitError" or status_code == 429:
        return HTTPException(
            429,
            "OpenAI rate, credit, or spending limit reached. Check the account limits and try again.",
        )
    if error_name in {
        "APIConnectionError", "APITimeoutError", "InternalServerError",
    } or status_code in {500, 502, 503, 504}:
        return HTTPException(
            503, "OpenAI is temporarily unavailable. Please try again shortly."
        )
    return HTTPException(500, "MaraPal encountered an internal error.")


def create_app(
    *, settings: Settings | None = None, graph_factory=build_graph,
    key_validator: Callable[[str], bool] = validate_openai_api_key,
    ask_rate_limiter: SlidingWindowRateLimiter | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    ask_rate_limiter = ask_rate_limiter or SlidingWindowRateLimiter()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        initialize(settings.monitoring_db)
        yield

    app = FastAPI(
        title="MaraPal Coach API", version="0.1.0",
        description="An evidence-aware running assistant by MaraPal.",
        lifespan=lifespan,
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/validate-key", response_model=KeyValidationResponse)
    def validate_key(
        openai_api_key: str | None = Header(
            default=None, alias="X-OpenAI-API-Key", include_in_schema=False,
        ),
    ) -> KeyValidationResponse:
        if not openai_api_key or not openai_api_key.strip():
            raise HTTPException(400, "Enter an OpenAI API key.")
        candidate = openai_api_key.strip()
        if len(candidate) > 512:
            raise HTTPException(400, "The OpenAI API key is too long.")
        if not key_validator(candidate):
            raise HTTPException(
                401, "The OpenAI API key is invalid or revoked."
            )
        return KeyValidationResponse(valid=True)

    @app.post("/api/v1/ask", response_model=AskResponse)
    def ask(
        payload: AskRequest,
        request: Request,
        openai_api_key: str | None = Header(
            default=None, alias="X-OpenAI-API-Key", include_in_schema=False,
        ),
        visitor_id: str | None = Header(
            default=None, alias="X-MaraPal-Visitor-ID", include_in_schema=False,
        ),
    ) -> AskResponse:
        if not openai_api_key or not openai_api_key.strip():
            raise HTTPException(401, "An OpenAI API key is required.")
        identifier = (visitor_id or "").strip()
        if not identifier or len(identifier) > 64:
            identifier = request.client.host if request.client else "unknown"
        allowed, retry_after = ask_rate_limiter.check(identifier)
        if not allowed:
            raise HTTPException(
                429,
                "Too many MaraPal questions. Please wait before asking again.",
                headers={"Retry-After": str(retry_after)},
            )

        interaction_id, trace_id = uuid4(), uuid4()
        started = time.perf_counter()
        try:
            # The credential is injected into provider clients, never into graph
            # state or tracing metadata, and is discarded after this request.
            application_graph = graph_factory(
                settings,
                retrieval_mode=settings.retrieval_mode,
                api_key=SecretStr(openai_api_key.strip()),
            )
            result = application_graph.invoke(
                {"question": payload.question},
                config={
                    "run_id": trace_id,
                    "run_name": "marapal-api-question",
                    "tags": ["api", "vector"],
                    "metadata": {"interaction_id": str(interaction_id)},
                },
            )
        except Exception as exc:
            record_interaction(
                settings.monitoring_db,
                interaction_id=str(interaction_id), trace_id=str(trace_id),
                question=payload.question,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                status="error", error_type=type(exc).__name__,
            )
            logger.error("MaraPal Coach graph invocation failed (%s)", type(exc).__name__)
            raise openai_http_error(exc) from exc
        record_interaction(
            settings.monitoring_db,
            interaction_id=str(interaction_id), trace_id=str(trace_id),
            question=payload.question,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            status="success", route=result["route"],
            answer_style=result["answer_style"], answer_detail=result["answer_detail"],
        )
        return AskResponse(
            answer=result["answer"], route=result["route"],
            retrieval_mode=settings.retrieval_mode,
            answer_style=result["answer_style"], answer_detail=result["answer_detail"],
            interaction_id=interaction_id, trace_id=trace_id,
            sources=result.get("sources", []),
        )

    @app.post("/api/v1/feedback", response_model=FeedbackResponse)
    def feedback(payload: FeedbackRequest) -> FeedbackResponse:
        try:
            trace_id = save_feedback(
                settings.monitoring_db, interaction_id=str(payload.interaction_id),
                rating=payload.rating, comment=payload.comment,
            )
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        synced = sync_langsmith_feedback(trace_id, payload.rating, payload.comment)
        return FeedbackResponse(saved=True, langsmith_synced=synced)

    @app.get("/api/v1/monitoring")
    def monitoring() -> dict[str, Any]:
        return dashboard(settings.monitoring_db)

    @app.get("/monitoring", response_class=HTMLResponse, include_in_schema=False)
    def monitoring_page() -> str:
        return render_dashboard(dashboard(settings.monitoring_db))

    return app


app = create_app()
