"""SQLite-backed exact filtering for time-sensitive race records."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

REGISTRATION_STATUSES = {
    "not_yet_open", "open", "late_only", "sold_out", "closed", "unknown"
}


class RaceFilters(BaseModel):
    start_date: str | None = Field(None, description="ISO YYYY-MM-DD")
    end_date: str | None = Field(None, description="ISO YYYY-MM-DD")
    city: str | None = None
    postcode_prefix: str | None = None
    min_distance_km: float | None = None
    max_distance_km: float | None = None
    registration_status: Literal[
        "not_yet_open", "open", "late_only", "sold_out", "closed", "unknown"
    ] | None = None
    limit: int = Field(
        default=10,
        ge=1,
        le=20,
        description="Number of results requested by the user; use 10 when unspecified",
    )


FILTER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Extract exact German race filters. Today is {today}. Do not guess a "
            "registration status. Leave optional filters null when the user did not "
            "specify them. Extract the requested number of results into limit.",
        ),
        ("human", "{question}"),
    ]
)


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE IF NOT EXISTS races (
        source TEXT NOT NULL, name TEXT NOT NULL, date TEXT NOT NULL,
        postcode TEXT, city TEXT, country TEXT NOT NULL,
        distance_min_km REAL, distance_max_km REAL, distances_raw TEXT,
        url TEXT NOT NULL, registration_status TEXT NOT NULL,
        registration_url TEXT, registration_checked_at TEXT, fetched_at TEXT NOT NULL,
        PRIMARY KEY (source, name, date, city)
        )"""
    )
    connection.execute("CREATE INDEX IF NOT EXISTS races_date_idx ON races(date)")
    return connection


def import_jsonl(connection: sqlite3.Connection, path: Path) -> int:
    sql = """INSERT OR REPLACE INTO races VALUES
    (:source,:name,:date,:postcode,:city,:country,:distance_min_km,:distance_max_km,
     :distances_raw,:url,:registration_status,:registration_url,
     :registration_checked_at,:fetched_at)"""
    count = 0
    with path.open(encoding="utf-8") as stream, connection:
        for line in stream:
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("registration_status") not in REGISTRATION_STATUSES:
                raise ValueError(f"invalid registration status: {item.get('registration_status')}")
            connection.execute(sql, item)
            count += 1
    return count


def search(connection: sqlite3.Connection, filters: RaceFilters) -> list[dict[str, Any]]:
    clauses, values = ["country = 'DE'"], []
    for column, operator, value in (
        ("date", ">=", filters.start_date), ("date", "<=", filters.end_date),
        ("distance_max_km", ">=", filters.min_distance_km),
        ("distance_min_km", "<=", filters.max_distance_km),
        ("registration_status", "=", filters.registration_status),
    ):
        if value is not None:
            clauses.append(f"{column} {operator} ?")
            values.append(value)
    if filters.city:
        clauses.append("city LIKE ?")
        values.append(f"%{filters.city}%")
    if filters.postcode_prefix:
        clauses.append("postcode LIKE ?")
        values.append(f"{filters.postcode_prefix}%")
    values.append(filters.limit)
    rows = connection.execute(
        f"SELECT * FROM races WHERE {' AND '.join(clauses)} ORDER BY date LIMIT ?", values
    ).fetchall()
    return [dict(row) for row in rows]


def format_races(races: list[dict[str, Any]]) -> str:
    if not races:
        return "I found no German races matching those exact filters."
    lines = ["Matching German races:"]
    for race in races:
        status = race["registration_status"]
        checked = race.get("registration_checked_at") or "not yet checked"
        link = race.get("registration_url") or race["url"]
        lines.append(
            f"- {race['date']} — {race['name']} ({race['city']}, "
            f"{race.get('distances_raw') or 'distance not listed'}). "
            f"Registration: {status}; checked: {checked}. {link}"
        )
    return "\n".join(lines)
