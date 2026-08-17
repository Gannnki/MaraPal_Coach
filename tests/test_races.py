import json
from pathlib import Path

from rag.races import RaceFilters, connect, import_jsonl, search


def test_import_and_exact_filter(tmp_path: Path):
    snapshot = tmp_path / "races.jsonl"
    records = [
        {
            "source": "dlv-laufkalender", "name": "Berlin 10K", "date": "2026-10-10",
            "postcode": "10115", "city": "Berlin", "country": "DE",
            "distance_min_km": 10.0, "distance_max_km": 10.0,
            "distances_raw": "10 Kilometer", "url": "https://example.test/berlin",
            "registration_status": "unknown", "registration_url": None,
            "registration_checked_at": None, "fetched_at": "2026-08-01T00:00:00+00:00",
        },
        {
            "source": "dlv-laufkalender", "name": "Munich Marathon", "date": "2026-10-12",
            "postcode": "80331", "city": "München", "country": "DE",
            "distance_min_km": 42.195, "distance_max_km": 42.195,
            "distances_raw": "42,195 Kilometer", "url": "https://example.test/munich",
            "registration_status": "open", "registration_url": "https://example.test/register",
            "registration_checked_at": "2026-08-12T12:00:00+00:00",
            "fetched_at": "2026-08-01T00:00:00+00:00",
        },
    ]
    snapshot.write_text("".join(json.dumps(item) + "\n" for item in records))
    with connect(tmp_path / "races.sqlite3") as connection:
        assert import_jsonl(connection, snapshot) == 2
        result = search(connection, RaceFilters(city="München", min_distance_km=40))
    assert [race["name"] for race in result] == ["Munich Marathon"]


def test_unknown_status_is_not_treated_as_open(tmp_path: Path):
    with connect(tmp_path / "races.sqlite3") as connection:
        connection.execute(
            """INSERT INTO races VALUES
            ('dlv','Race','2026-09-01','10115','Berlin','DE',10,10,'10 km',
             'https://example.test','unknown',NULL,NULL,'2026-08-01')"""
        )
        assert search(connection, RaceFilters(registration_status="open")) == []


def test_connections_can_be_opened_in_separate_request_scopes(tmp_path: Path):
    database = tmp_path / "races.sqlite3"
    with connect(database) as first:
        first.execute(
            """INSERT INTO races VALUES
            ('dlv','Race','2026-09-01','10115','Berlin','DE',10,10,'10 km',
             'https://example.test','unknown',NULL,NULL,'2026-08-01')"""
        )
    with connect(database) as second:
        assert len(search(second, RaceFilters(city="Berlin"))) == 1


def test_search_honors_requested_result_limit(tmp_path: Path):
    database = tmp_path / "races.sqlite3"
    with connect(database) as connection:
        for day in ("01", "02"):
            connection.execute(
                """INSERT INTO races VALUES
                ('dlv', ?, ?, '10115', 'Berlin', 'DE', 10, 10, '10 km',
                 ?, 'unknown', NULL, NULL, '2026-08-01')""",
                (f"Race {day}", f"2026-09-{day}", f"https://example.test/{day}"),
            )
        result = search(connection, RaceFilters(city="Berlin", limit=1))

    assert len(result) == 1
    assert result[0]["name"] == "Race 01"
