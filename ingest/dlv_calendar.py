"""Fetch and normalise the DLV running calendar from laufen.de.

The calendar is the official event register of the Deutscher Leichtathletik-Verband:
every run sanctioned by one of the 19 regional athletics associations appears here.
It is served by an undocumented AJAX endpoint that returns a JSON envelope whose
`events` field is a block of HTML teasers, one per event.

What this gives you: the event universe -- name, date, place, distances, organiser link.
What it does NOT give you: registration status, deadline or price. See
`data/raw/README.md` for why that gap exists and how it is filled.

Usage:
    python ingest/dlv_calendar.py --out data/raw/races/dlv/$(date +%%F).jsonl
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Iterator

ENDPOINT = "https://www.laufen.de/dlv-laufkalender/ajax"
DETAIL_BASE = "https://www.laufen.de/"
USER_AGENT = "MaraPal/0.1 (running event aggregator; +https://github.com/)"

# One teaser block per event. The href is either an internal detail page or the
# organiser's own website -- which one you get is not consistent across events.
TEASER_RE = re.compile(r'<a href="([^"]*)"(.*?)class="teaser event">(.*?)</a>', re.S)
DATE_RE = re.compile(r'class="date">\s*([^<]+?)\s*<')
HEADLINE_RE = re.compile(r'class="headline[^"]*">\s*(.*?)\s*</div>', re.S)
LOCATION_RE = re.compile(r'class="location">\s*(.*?)\s*</div>', re.S)
STRECKEN_RE = re.compile(r"Strecken:\s*([^<]+?)\s*<")
CODE_RE = re.compile(r'class="code">\s*([^<]+?)\s*<')
# "87730 Bad Grönenbach" -- German postcodes are always five digits.
PLACE_RE = re.compile(r"^(\d{5})\s+(.*)$")


def fetch() -> dict:
    """Call the calendar endpoint and return the parsed JSON envelope.

    The endpoint exposes filters (date range, radius, distance) on its `user`
    object, but they are session state -- passing them as GET or POST parameters
    is ignored and the full calendar comes back regardless. So we take the whole
    thing in one request and filter locally, which is what we want anyway.
    """
    req = urllib.request.Request(
        ENDPOINT,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _text(match: re.Match | None) -> str:
    if not match:
        return ""
    return html.unescape(re.sub(r"<[^>]+>", " ", match.group(1))).strip()


def _parse_distances(strecken: str) -> tuple[float | None, float | None]:
    """'0,35 bis 10 Kilometer' -> (0.35, 10.0). German decimal comma."""
    nums = [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:,\d+)?", strecken)]
    if not nums:
        return None, None
    return min(nums), max(nums)


def parse_events(payload: dict) -> Iterator[dict]:
    """Yield one normalised record per event teaser in the payload."""
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    for match in TEASER_RE.finditer(payload.get("events", "")):
        href, _attrs, body = match.groups()
        date_raw = _text(DATE_RE.search(body))
        try:
            date = dt.datetime.strptime(date_raw, "%d.%m.%Y").date().isoformat()
        except ValueError:
            # A malformed date makes the record useless for filtering; skip it
            # rather than let it through and fail a date comparison later.
            continue

        place = _text(LOCATION_RE.search(body))
        pm = PLACE_RE.match(place)
        strecken = _text(STRECKEN_RE.search(body))
        dist_min, dist_max = _parse_distances(strecken)

        is_external = href.lower().startswith("http")
        yield {
            "source": "dlv-laufkalender",
            "name": _text(HEADLINE_RE.search(body)),
            "date": date,
            "postcode": pm.group(1) if pm else None,
            "city": pm.group(2) if pm else place,
            "country": "DE",
            "distances_raw": strecken,
            "distance_min_km": dist_min,
            "distance_max_km": dist_max,
            "ranked_distances": [html.unescape(c) for c in CODE_RE.findall(body)],
            "url": href if is_external else DETAIL_BASE + href.lstrip("/"),
            "url_is_organiser": is_external,
            # Deliberately unresolved here. The calendar does not carry it, and
            # guessing "open because the date is in the future" is how you send
            # someone to a sold-out race. Filled by a separate enrichment step.
            "registration_status": "unknown",
            "registration_url": None,
            "registration_checked_at": None,
            "fetched_at": fetched_at,
        }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True, help="output .jsonl path")
    ap.add_argument("--start", type=dt.date.fromisoformat, default=None,
                    help="drop events before this date (filtered locally)")
    ap.add_argument("--end", type=dt.date.fromisoformat, default=None,
                    help="drop events after this date (filtered locally)")
    args = ap.parse_args()

    payload = fetch()
    records = list(parse_events(payload))
    parsed_total = len(records)

    if args.start:
        records = [r for r in records if r["date"] >= args.start.isoformat()]
    if args.end:
        records = [r for r in records if r["date"] <= args.end.isoformat()]

    declared = payload.get("results")
    if declared and declared != parsed_total:
        # The endpoint reports a total that exceeds what it renders in one
        # response. Say so loudly: a silent shortfall reads as full coverage.
        print(
            f"warning: endpoint declared {declared} results but only "
            f"{parsed_total} were parsed ({declared - parsed_total} missing)",
            file=sys.stderr,
        )
    if parsed_total != len(records):
        print(f"date filter kept {len(records)} of {parsed_total} events", file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"wrote {len(records)} events to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
