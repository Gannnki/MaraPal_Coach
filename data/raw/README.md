# Raw data

This directory holds source material before normalisation. Two kinds, with very different handling.

## 1. The running.wiki bundle

The knowledge base is an MIT-licensed markdown repository. **Clone it, do not scrape the website** — the repo is the authored form, with frontmatter and citation links intact, and the rendered site is a lossy view of it.

```bash
git clone https://github.com/jacquescorbytuech/running-knowledge-base data/raw/running-wiki
```

Pin to a commit rather than tracking `main`, so a knowledge-base update never silently changes your answers between evaluation runs. Record the commit SHA alongside the processed output.

### What you get

| Directory | Files | Contents |
|---|---|---|
| `concepts/` | 39 | Physiology and theory — VO₂max, lactate threshold, running economy, durability; also population pages (the female runner, masters, youth) |
| `techniques/` | 43 | Training methods — intervals, tapering, periodisation, polarised training, the long run |
| `nutrition/` | 42 | Fuelling and supplements, graded honestly — caffeine, nitrate, bicarbonate, iron, RED-S |
| `recovery/` | 21 | Sleep, overtraining, recovery modalities, monitoring |
| `injury/` | 19 | Common running injuries and management |
| `gear/` | 18 | Super-shoes, foams, plates, GPS-watch metrics |
| `events/` | 9 | Racing distances as units — 800m through the marathon, cross country |
| `entities/` | 11 | Coaches and scientists behind the methods |
| `sources/` | 620 | Provenance anchors — one page per cited paper, review or consensus statement |

### Page schema

Every page carries YAML frontmatter. Content pages:

```yaml
---
type: Concept          # Concept | Technique | Substance | Gear | Event | Metric | Entity
title: Lactate threshold
description: One-line summary.
tags: [physiology]     # physiology | training | nutrition | recovery | gear | injury
evidence: strong       # strong | moderate | limited | weak | contested
timestamp: 2026-06-24
---
```

Source pages:

```yaml
---
type: Source
title: Abbiss & Laursen 2008, describing and understanding pacing strategies
resource: https://link.springer.com/article/10.2165/...   # link to the primary material
tags: [training]
timestamp: 2026-06-24
---
```

### Ingest notes

- **One concept per file** — the file is the natural chunk boundary. Split further only for long pages, and keep the frontmatter attached to every chunk.
- **Citations are relative links** (`[Faude et al. 2009](../sources/faude-2009-lactate-thresholds.md)`). Resolve these to running.wiki URLs or to source-page records during processing, or they break once the text leaves the repo.
- **The `evidence` grade must survive into retrieval metadata.** It is the point of the whole exercise; a chunk that loses its grade is worse than useless because it reads as confident.
- **`index.md` files are navigation, not content.** Exclude them from the knowledge index.
- **Evidence callouts** (`> [!success] Evidence: strong`) sit directly below each heading and restate the grade in prose. Keep them with their page.

## 2. German race calendar

Scope is Germany. Store dated snapshots so a sync can be replayed and diffed.

```
races/
└── dlv/
    └── 2026-07-30.jsonl
```

Unlike the wiki, this data **expires**. A race that has happened, filled up, or closed registration is actively misleading. Freshness is a correctness property: every record carries a `fetched_at`, and the sync runs on a schedule.

### Primary source: the DLV-Laufkalender

`ingest/dlv_calendar.py` fetches and normalises it. Run:

```bash
python ingest/dlv_calendar.py --out data/raw/races/dlv/$(date +%F).jsonl
```

It calls an undocumented AJAX endpoint, `https://www.laufen.de/dlv-laufkalender/ajax`, which returns a JSON envelope whose `events` field is a block of HTML teasers. Server-side filters exist on the `user` object: `start` and `end` (unix timestamps), `radius`, `distanceStart`/`distanceEnd`, and `search`.

Being undocumented, it can change without notice. The parser is regex over markup — if it starts returning zero events, the markup moved. That is the expected failure mode and it is loud, not silent.

**Known shortfall:** the endpoint declares ~1,396 results but renders ~1,111 parseable teasers in a single response. The script prints a warning naming the gap rather than reporting apparent full coverage. Worth investigating whether the remainder is behind pagination.

Verified yield as of 2026-07-30: 1,111 events, 1,104 with postcodes, 917 with parsed distances, spanning to November 2027. About 1,000 of the 1,000-odd entries link to an organiser's own site rather than a `laufen.de` detail page.

### Source assessment

| Source | Coverage | Registration status | Usable |
|---|---|---|---|
| [laufen.de / DLV](https://www.laufen.de/laufkalender) | ~1,400 sanctioned German events | No | **Yes** — official, free, permissive `robots.txt` (only `/contao/` disallowed) |
| [runme.de](https://www.runme.de) | Largest German-language calendar | — | **No.** Its `robots.txt` explicitly blocks `GPTBot`, `OpenAI` and `CCBot`. Do not ingest it |
| [ahotu](https://www.ahotu.com) | 60,000 races, 194 countries, has registration data | Yes | Not without permission — Cloudflare-protected and the API is partner/commercial. Worth approaching if the project gets serious |
| [raceresult](https://www.raceresult.com) | Events hosted on their platform; German company, GDPR-hosted | Yes, for its own events | Possible — API access needs to be arranged with them |
| Organiser websites | Per event | Authoritative | Yes, but every site differs |

`runme.de` is the one to be careful about: it has the best coverage and has explicitly opted out of AI crawling. Respect it.

### The registration gap

The calendar does not carry registration status, deadline or price. `ingest/dlv_calendar.py` therefore sets `registration_status: "unknown"` rather than inferring it — a future date does not mean a race has places left.

Resolving it is a separate enrichment step, and the cheap correct version is lazy: resolve on demand for events a user actually asks about, cache the result with a timestamp, and re-check on a short TTL. Do not try to crawl 1,100 organiser sites nightly.

German races complicate the boolean: past the `Meldeschluss` most events still accept a `Nachmeldung` online with a surcharge, at the expo, or on race morning. The status ladder (`not_yet_open` / `open` / `late_only` / `sold_out` / `closed` / `unknown`) is defined in `README.md`. `sold_out` is the status that actually stops a runner.

### Record schema

Produced by `ingest/dlv_calendar.py`:

| Field | Notes |
|---|---|
| `name`, `date` | `date` is ISO 8601 |
| `postcode`, `city`, `country` | German postcodes are five digits; geocode them for radius search |
| `distances_raw` | Source string, e.g. `"0,35 bis 10 Kilometer"` — note the German decimal comma |
| `distance_min_km`, `distance_max_km` | Parsed floats; `null` when the source omits them |
| `ranked_distances` | Official ranked competitions, e.g. `["5 km", "10 km"]` |
| `url`, `url_is_organiser` | Detail page or the organiser's own site |
| `registration_status`, `registration_url`, `registration_checked_at` | Filled by enrichment, not by the calendar fetch |
| `fetched_at` | UTC, ISO 8601 |

Coordinates are not in the source. Geocode from postcode during processing — radius search is the most common filter and it cannot be done on a postcode string.

## What not to commit here

- Race API responses containing participant or registrant personal data — fetch event metadata only
- Any scraped article text from third-party running sites. The wiki's MIT licence is what makes this project clean; do not dilute it with material you have no right to redistribute
