"""Local interaction metrics and user feedback for the monitoring dashboard."""

from __future__ import annotations

import datetime as dt
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 10000")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize(path: Path) -> None:
    with _connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS interactions (
                id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                question TEXT NOT NULL,
                route TEXT,
                answer_style TEXT,
                answer_detail TEXT,
                latency_ms REAL NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('success', 'error')),
                error_type TEXT
            );
            CREATE INDEX IF NOT EXISTS interactions_created_idx
                ON interactions(created_at);
            CREATE TABLE IF NOT EXISTS feedback (
                interaction_id TEXT PRIMARY KEY
                    REFERENCES interactions(id) ON DELETE CASCADE,
                rating INTEGER NOT NULL CHECK (rating IN (-1, 1)),
                comment TEXT,
                created_at TEXT NOT NULL
            );
            """
        )


def record_interaction(
    path: Path, *, interaction_id: str, trace_id: str, question: str,
    latency_ms: float, status: str, route: str | None = None,
    answer_style: str | None = None, answer_detail: str | None = None,
    error_type: str | None = None,
) -> None:
    with _connect(path) as connection:
        connection.execute(
            """INSERT INTO interactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                interaction_id, trace_id, dt.datetime.now(dt.UTC).isoformat(), question,
                route, answer_style, answer_detail, latency_ms, status, error_type,
            ),
        )


def save_feedback(
    path: Path, *, interaction_id: str, rating: int, comment: str | None = None,
) -> str:
    with _connect(path) as connection:
        row = connection.execute(
            "SELECT trace_id FROM interactions WHERE id = ?", (interaction_id,)
        ).fetchone()
        if row is None:
            raise ValueError("interaction not found")
        connection.execute(
            """INSERT INTO feedback VALUES (?, ?, ?, ?)
            ON CONFLICT(interaction_id) DO UPDATE SET
                rating = excluded.rating,
                comment = excluded.comment,
                created_at = excluded.created_at""",
            (
                interaction_id, rating, comment,
                dt.datetime.now(dt.UTC).isoformat(),
            ),
        )
        return str(row["trace_id"])


def sync_langsmith_feedback(trace_id: str, rating: int, comment: str | None) -> bool:
    tracing = os.getenv("LANGSMITH_TRACING", "").lower() in {"1", "true", "yes"}
    if not tracing or not os.getenv("LANGSMITH_API_KEY"):
        return False
    try:
        from langsmith import Client

        identifier = UUID(trace_id)
        Client().create_feedback(
            key="user_rating",
            score=1.0 if rating == 1 else 0.0,
            comment=comment,
            run_id=identifier,
            trace_id=identifier,
        )
        return True
    except Exception:
        logger.exception("Local feedback saved, but LangSmith synchronization failed")
        return False


def dashboard(path: Path) -> dict[str, Any]:
    with _connect(path) as connection:
        def rows(sql: str) -> list[dict[str, Any]]:
            return [dict(row) for row in connection.execute(sql).fetchall()]

        totals = dict(
            connection.execute(
                """SELECT COUNT(*) AS requests,
                ROUND(AVG(latency_ms), 2) AS avg_latency_ms,
                SUM(status = 'error') AS errors
                FROM interactions"""
            ).fetchone()
        )
        feedback = dict(
            connection.execute(
                """SELECT COUNT(*) AS responses,
                ROUND(100.0 * AVG(rating = 1), 1) AS positive_rate
                FROM feedback"""
            ).fetchone()
        )
        return {
            "totals": totals | feedback,
            "requests_by_day": rows(
                """SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS requests
                FROM interactions GROUP BY day ORDER BY day"""
            ),
            "routes": rows(
                """SELECT COALESCE(route, 'unknown') AS route, COUNT(*) AS requests
                FROM interactions GROUP BY route ORDER BY requests DESC"""
            ),
            "styles": rows(
                """SELECT COALESCE(answer_style, 'unknown') AS style, COUNT(*) AS requests
                FROM interactions GROUP BY answer_style ORDER BY requests DESC"""
            ),
            "latency_by_route": rows(
                """SELECT COALESCE(route, 'unknown') AS route,
                ROUND(AVG(latency_ms), 2) AS avg_latency_ms
                FROM interactions GROUP BY route ORDER BY avg_latency_ms DESC"""
            ),
            "ratings": rows(
                """SELECT CASE rating WHEN 1 THEN 'positive' ELSE 'negative' END AS rating,
                COUNT(*) AS responses FROM feedback GROUP BY rating ORDER BY rating"""
            ),
            "statuses": rows(
                """SELECT status, COUNT(*) AS requests FROM interactions
                GROUP BY status ORDER BY status"""
            ),
        }
