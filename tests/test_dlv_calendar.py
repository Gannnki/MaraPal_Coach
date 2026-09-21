import json
from pathlib import Path

from ingest import dlv_calendar


def teaser(href: str, date: str, name: str, place: str, strecken: str | None) -> str:
    distances = (
        f'<div class="info wettbewerbe">\n  {strecken}\n</div>' if strecken else ""
    )
    return f"""<a href="{href}" class="teaser event">
  <div class="inner"><div class="tcontainer">
    <div class="date">{date}</div>
    <div class="info">
      <div class="headline noline">{name}</div>
      <div class="location">
        {place}
      </div>
    </div>
    <div class="strecken">{distances}</div>
  </div></div>
</a>"""


def test_parse_events_reads_single_and_multiple_distances_and_skips_repeats():
    html = "".join([
        teaser("laufkalender/details/a", "9.10.2026", "Multi", "71034   Böblingen",
               "Strecken: 0,4 bis 10 Kilometer"),
        teaser("laufkalender/details/b", "22.9.2026", "Single", "77716   Haslach",
               "Strecke: 5 Kilometer"),
        teaser("laufkalender/details/c", "1.11.2026", "No distances", "Bremen", None),
        teaser("laufkalender/details/a", "9.10.2026", "Multi", "71034   Böblingen",
               "Strecken: 0,4 bis 10 Kilometer"),
    ])

    records = {r["name"]: r for r in dlv_calendar.parse_events({"events": html})}

    assert list(records) == ["Multi", "Single", "No distances"]
    assert (records["Multi"]["distance_min_km"], records["Multi"]["distance_max_km"]) == (0.4, 10.0)
    assert (records["Single"]["distance_min_km"], records["Single"]["distance_max_km"]) == (5.0, 5.0)
    assert records["No distances"]["distance_max_km"] is None
    assert records["Single"]["date"] == "2026-09-22"
    assert records["Single"]["url"] == "https://laufen.de/laufkalender/details/b"
    assert records["No distances"]["postcode"] is None
    # Never inferred from the date; the calendar carries no registration data.
    assert {r["registration_status"] for r in records.values()} == {"unknown"}


def test_fetch_walks_every_page_and_keeps_promoted_events(monkeypatch):
    pages = {
        1: {"pages": 3, "total": 3, "topevents": "TOP", "events": "P1"},
        2: {"pages": 3, "total": 3, "events": "P2"},
        3: {"pages": 3, "total": 3, "events": "P3"},
    }
    requested: list[int] = []

    def fake_fetch_page(page: int) -> dict:
        requested.append(page)
        return pages[page]

    monkeypatch.setattr(dlv_calendar, "fetch_page", fake_fetch_page)
    monkeypatch.setattr(dlv_calendar, "PAGE_DELAY_SECONDS", 0)

    payload = dlv_calendar.fetch()

    assert requested == [1, 2, 3]
    assert payload == {"events": "TOPP1P2P3", "total": 3}


def test_main_refuses_to_overwrite_a_snapshot_when_nothing_parses(
    tmp_path: Path, monkeypatch, capsys
):
    out = tmp_path / "races.jsonl"
    out.write_text('{"keep": "previous snapshot"}\n')
    monkeypatch.setattr(dlv_calendar, "fetch", lambda: {"events": "<html>moved</html>", "total": 0})
    monkeypatch.setattr("sys.argv", ["dlv_calendar.py", "--out", str(out)])

    assert dlv_calendar.main() == 1

    assert json.loads(out.read_text()) == {"keep": "previous snapshot"}
    assert "no events parsed" in capsys.readouterr().err


def test_main_warns_when_parsed_count_differs_from_declared_total(
    tmp_path: Path, monkeypatch, capsys
):
    html = teaser("laufkalender/details/a", "9.10.2026", "Only one", "71034 Böblingen",
                  "Strecke: 10 Kilometer")
    monkeypatch.setattr(dlv_calendar, "fetch", lambda: {"events": html, "total": 5})
    out = tmp_path / "races.jsonl"
    monkeypatch.setattr("sys.argv", ["dlv_calendar.py", "--out", str(out)])

    assert dlv_calendar.main() == 0

    assert "declared 5 events but 1 were parsed" in capsys.readouterr().err
    assert len(out.read_text().splitlines()) == 1
