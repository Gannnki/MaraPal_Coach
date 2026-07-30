# MaraPal
# A running knowledge Q&A system with race discovery

## Background

Running advice is abundant and mostly unreliable. Training guidance is scattered across blogs, forums, brand content, and podcasts, where marketing claims and folklore sit next to genuine science with nothing to distinguish them. A runner asking a simple question — is beetroot juice worth it, how long should my taper be, does this shoe actually help — has no easy way to tell a meta-analysis from a press release.

MaraPal is a retrieval-augmented generation (RAG) question-answering system built on [running.wiki](https://running.wiki), an evidence-graded knowledge base on distance running. Every claim in the source material carries an explicit evidence grade and cites a source at the point it is made, so answers can be both grounded and honest about how well-supported they are.

Alongside the Q&A, MaraPal answers the question that prompted the project: **which running events in Germany can I still enter?** It covers German races by date, location, distance, and registration status.

## What it does

**Evidence-graded Q&A.** Ask in natural language:

- "How much of my training should be easy?"
- "Does sodium bicarbonate actually work?"
- "What's the difference between LT1 and LT2?"
- "How long before a marathon should I taper?"
- "Do carbon-plated shoes help a 4-hour marathoner?"

Answers cite their sources and carry the underlying evidence grade, so a `strong` claim and a `weak` one are not presented with the same confidence.

**Race discovery (Germany).** Find events you can still enter and get to the registration page:

- "Half marathons within 50km of Munich in the next three months"
- "Autumn marathons in Germany still open for entry"
- "Beginner-friendly 10Ks in Bayern this spring"
- "What can I still sign up for in October?"

## Data sources

| Type | Source | Licence / notes |
|---|---|---|
| Core knowledge base | [running.wiki](https://running.wiki) — source repo [jacquescorbytuech/running-knowledge-base](https://github.com/jacquescorbytuech/running-knowledge-base) | **MIT licensed.** 202 articles across concepts, techniques, nutrition, gear, recovery, injury, events, entities, plus 620 source pages. Cloned, not scraped |
| Citation layer | The `sources/` directory of the same repo | Each page records the primary material (paper, review, consensus statement) behind a claim, with a link to the original |
| German race calendar | [DLV-Laufkalender on laufen.de](https://www.laufen.de/laufkalender) | The official register of the Deutscher Leichtathletik-Verband: every run sanctioned by one of the 19 regional associations. ~1,400 events. Free JSON endpoint, permissive `robots.txt` |
| Registration status | Organiser and timing-platform pages, resolved per event | Not present in the calendar; see below |

The knowledge base is the whole reason the project works. Its editorial rules — no affiliate links, no brand promotion, every empirical claim sourced, evidence graded honestly — are exactly the properties a RAG system needs and almost never gets from scraped web content.

### Evidence grades

Grades come from the upstream wiki and are carried through retrieval into the answer:

| Grade | Meaning |
|---|---|
| `strong` | consistent RCTs, meta-analyses or consensus statements; safe to act on |
| `moderate` | several supporting studies, with caveats |
| `limited` | thin, preliminary or mixed support |
| `weak` | little credible support; marketed beyond the evidence |
| `contested` | genuine disagreement in the literature |

### Registration status: the hard part

No free German source publishes "can I still enter this race". The DLV calendar gives the event universe — name, date, place, distances, organiser link — and stops there. Around 90% of its entries link straight out to the organiser's own website, and each of those is a different page.

German practice also makes the question less binary than it sounds. Past the official `Meldeschluss`, most events still take a `Nachmeldung` — online with a surcharge, at the expo, often up to an hour before the start. So the status is a ladder, not a flag:

| Status | Meaning |
|---|---|
| `not_yet_open` | Registration has not opened |
| `open` | Regular registration |
| `late_only` | Past `Meldeschluss`, `Nachmeldung` accepted, usually with a fee |
| `sold_out` | Field limit reached — the real blocker |
| `closed` | No entry of any kind |
| `unknown` | Not yet resolved |

The system never asserts `open` from the event date alone. An unresolved event is reported as `unknown` with its registration link and the time it was last checked. A stale "yes, still open" costs a runner a wasted plan; "here is the link, checked 6 hours ago" is never wrong.

## Architecture

Two subsystems behind one interface, because the two kinds of question need different retrieval:

```
                        ┌─ knowledge question ─→ vector store ─→ RAG answer + citations
   user query ─→ router ─┤
                        └─ race question ──────→ structured store ─→ filtered event list
```

Knowledge is static prose, retrieved semantically. Race data is time-sensitive structured records, retrieved by exact filters on date, location, distance, and price. Running race lookup through a vector store would return races that *sound* similar rather than races that *match*, so the two stay separate and the router decides which to use.

## Project structure

```
MaraPal/
├── data/
│   ├── raw/          # Cloned running.wiki bundle; fetched race-calendar snapshots
│   └── processed/    # Unified jsonl knowledge entries; normalised event records
├── ingest/           # Wiki parsing, chunking, embedding, index building; race-data sync
├── rag/              # Query routing, retrieval, prompt construction, LLM call
├── eval/             # Retrieval and generation quality evaluation
├── app/              # Web interface
├── docker/           # Container configuration
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Technical architecture (planned)

- Vector store: TBD (candidates: Qdrant / Elasticsearch)
- Structured store for events: TBD (Postgres or SQLite is sufficient)
- Embedding model: TBD (open-source sentence embedding model)
- LLM: TBD
- Interface: Streamlit / FastAPI
- Monitoring: self-hosted logging + Grafana

## Attribution

The knowledge base is MIT licensed. The licence and copyright notice must be preserved in any distribution, and answers should credit running.wiki as the source. MaraPal is not affiliated with running.wiki.

Not medical or coaching advice. People respond differently to training; treat even well-evidenced claims as a starting point to test on yourself.

## Running the project


## Evaluation results


## Monitoring and feedback

