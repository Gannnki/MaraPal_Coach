"""Dependency-free HTML rendering for the separate monitoring dashboard."""

from __future__ import annotations

from html import escape
from typing import Any


def _chart(title: str, rows: list[dict[str, Any]], label: str, value: str) -> str:
    maximum = max((float(row.get(value) or 0) for row in rows), default=0) or 1
    bars = []
    for row in rows:
        number = float(row.get(value) or 0)
        width = max(2, round(number / maximum * 100)) if number else 0
        display = f"{number:,.2f}".rstrip("0").rstrip(".")
        bars.append(
            '<div class="bar-row">'
            f'<span class="label">{escape(str(row.get(label, "unknown")))}</span>'
            f'<span class="track"><span class="bar" style="width:{width}%"></span></span>'
            f'<strong>{display}</strong></div>'
        )
    content = "".join(bars) or '<p class="empty">No data yet.</p>'
    return f'<section class="chart"><h2>{escape(title)}</h2>{content}</section>'


def render_dashboard(report: dict[str, Any]) -> str:
    totals = report["totals"]
    positive = totals.get("positive_rate")
    latency = totals.get("avg_latency_ms")
    metrics = (
        ("Requests", totals.get("requests") or 0),
        ("Feedback responses", totals.get("responses") or 0),
        ("Positive feedback", f"{positive:.1f}%" if positive is not None else "N/A"),
        ("Average latency", f"{latency:.0f} ms" if latency is not None else "N/A"),
    )
    cards = "".join(
        f'<div class="metric"><span>{escape(label)}</span><strong>{escape(str(value))}</strong></div>'
        for label, value in metrics
    )
    charts = "".join(
        (
            _chart("1. Requests by day", report["requests_by_day"], "day", "requests"),
            _chart("2. Route distribution", report["routes"], "route", "requests"),
            _chart("3. Answer style", report["styles"], "style", "requests"),
            _chart(
                "4. Average latency by route", report["latency_by_route"],
                "route", "avg_latency_ms",
            ),
            _chart("5. User feedback", report["ratings"], "rating", "responses"),
            _chart("6. Request status", report["statuses"], "status", "requests"),
        )
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<meta http-equiv="refresh" content="30"><title>MaraPal Coach Monitoring</title>
<style>
:root{{--bg:#0e1117;--panel:#171c26;--text:#f5f7fb;--muted:#9ca7b8;--accent:#7c5cff}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font:15px system-ui}}
main{{max-width:1200px;margin:auto;padding:32px}} h1{{margin:0 0 6px}} .subtitle,.empty{{color:var(--muted)}}
.metrics,.grid{{display:grid;gap:16px}} .metrics{{grid-template-columns:repeat(4,1fr);margin:28px 0}}
.grid{{grid-template-columns:repeat(2,1fr)}} .metric,.chart{{background:var(--panel);border:1px solid #293142;border-radius:12px;padding:20px}}
.metric span{{display:block;color:var(--muted)}} .metric strong{{display:block;font-size:28px;margin-top:8px}}
.chart h2{{font-size:17px;margin:0 0 20px}} .bar-row{{display:grid;grid-template-columns:110px 1fr 70px;gap:10px;align-items:center;margin:12px 0}}
.label{{overflow:hidden;text-overflow:ellipsis}} .track{{height:12px;background:#293142;border-radius:8px;overflow:hidden}}
.bar{{display:block;height:100%;background:linear-gradient(90deg,var(--accent),#31c4f3);border-radius:8px}}
@media(max-width:800px){{.metrics,.grid{{grid-template-columns:1fr}}}}
</style></head><body><main><h1>MaraPal Coach Monitoring</h1>
<p class="subtitle">Operational metrics and user feedback · refreshes every 30 seconds</p>
<div class="metrics">{cards}</div><div class="grid">{charts}</div></main></body></html>"""
