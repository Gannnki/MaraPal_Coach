# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

Early scaffold. One working script exists; everything else is empty.

```bash
# Fetch and normalise the German race calendar (no dependencies beyond stdlib)
python ingest/dlv_calendar.py --out data/raw/races/dlv/$(date +%F).jsonl
```

`rag/`, `eval/`, `app/` and `docker/` are empty, and `docker-compose.yml` is planned but does not exist. There is no test suite and no lint config yet — do not invent commands for them; add real ones as the code lands.

`requirements.txt` is a comment-only stub listing intended dependency *categories*, not pinned packages.

`requirements.txt` is a comment-only stub listing intended dependency *categories*, not pinned packages.

## What this project is

MaraPal is a chatbot with two jobs: answer running-training questions from [running.wiki](https://running.wiki), and tell the user **which running events in Germany they can still enter**.

Race scope is Germany only. Do not add US sources — an earlier draft of this file recommended RunSignup, which is US-focused and near-useless here.

The project was originally scoped as a women-specific marathon RAG and was re-scoped to general running on 2026-07-30. Women's-health topics are still covered — they are part of the upstream knowledge base (`concepts/the-female-runner.md`, `concepts/menstrual-cycle-and-training.md`, `concepts/pregnancy-and-postpartum-running.md`, `nutrition/red-s.md`, `nutrition/iron.md`) — they are simply no longer the exclusive focus.

## The two-subsystem split — the central design decision

Knowledge questions and race questions need different retrieval, and conflating them is the main way this project can go wrong.

```
                        ┌─ knowledge question ─→ vector store ─→ RAG answer + citations
   user query ─→ router ─┤
                        └─ race question ──────→ structured store ─→ filtered event list
```

**Knowledge** is static prose. Semantic retrieval is correct. Answers must carry citations and an evidence grade.

**Race data** is time-sensitive structured records. Retrieval is exact filtering — date range, geographic radius, distance, price, registration status. Do **not** put race listings in the vector store: "marathons within 100km in October" is a filter, and semantic similarity would return races that *sound* alike rather than races that *match*. Use a relational store and let the LLM call it as a tool.

A race record that is stale is not merely unhelpful, it is wrong — a runner can miss a registration deadline. Freshness is a correctness property, not a nice-to-have. Every event record carries a fetch timestamp.

### Never infer registration status from the date

This is the rule most likely to be broken by accident, because inferring is easy and looks right in testing.

The DLV calendar carries no registration status. `ingest/dlv_calendar.py` writes `registration_status: "unknown"` and leaves it. A future event date does **not** mean entry is open — the race may be sold out, which is the case a runner most needs to know about.

Two consequences for anything built on top:

- Resolve status **lazily**, for events a user actually asks about, and cache with a timestamp. Do not crawl ~1,100 organiser sites on a schedule.
- When status is `unknown`, say so and give the registration link with a last-checked time. Never let the LLM smooth `unknown` into "yes, still open" — that is the failure mode that wastes the user's plans.

German events use a status ladder rather than a boolean, because past the `Meldeschluss` most still accept a `Nachmeldung` (with a surcharge, at the expo, sometimes on race morning): `not_yet_open` / `open` / `late_only` / `sold_out` / `closed` / `unknown`.

### Source constraint

[runme.de](https://www.runme.de) has the best German coverage and its `robots.txt` explicitly blocks `GPTBot`, `OpenAI` and `CCBot`. It has opted out of AI use. Do not ingest it, however tempting the coverage. Full source assessment is in `data/raw/README.md`.

## Upstream: running.wiki

Source repo: [jacquescorbytuech/running-knowledge-base](https://github.com/jacquescorbytuech/running-knowledge-base), **MIT licensed**, ~200 content articles plus 620 source pages, authored as markdown with YAML frontmatter.

**Clone the repo; never scrape the site.** The repo is the authored form with frontmatter and citation links intact. Pin to a commit rather than tracking `main`, and record the SHA with the processed output — otherwise an upstream edit silently changes your answers between evaluation runs.

Full schema, directory breakdown, and ingest notes are in `data/raw/README.md`. The three rules that matter most:

1. **The `evidence` grade must survive into retrieval metadata and into the answer.** The upstream wiki's entire value is that it grades claims honestly (`strong` / `moderate` / `limited` / `weak` / `contested`). A chunk that arrives at generation time without its grade is worse than no chunk, because it reads as confident. If the retrieved context is `weak`, the answer must say so.
2. **Preserve the citation chain.** Claims link to pages under `sources/`, which link to the primary paper. Relative markdown links (`../sources/foo.md`) break once text leaves the repo — resolve them during processing.
3. **One concept per file** — the file is the natural chunk boundary. Exclude `index.md` files; they are navigation, not content.

The upstream editorial line is non-commercial: no affiliate links, no brand promotion, no buyer's guides. Inheriting that is deliberate. Do not add product recommendations or affiliate links to generated answers — it would break the licence's spirit and destroy the trust property the knowledge base exists to provide.

## Attribution and licence

MIT requires the licence and copyright notice be preserved in distribution. Answers should credit running.wiki. Race platform APIs (RunSignup is Apache-licensed) have their own attribution terms — check before shipping.

Every health, injury, or nutrition page upstream carries a "Not medical advice" warning. Generated answers on those topics should carry the equivalent.

## Undecided technology choices

Do not assume a stack:

| Layer | Candidates |
|---|---|
| Vector store | Qdrant or Elasticsearch |
| Event store | Postgres or SQLite (SQLite is sufficient at this scale) |
| Embeddings | an open-source sentence embedding model (undecided) |
| LLM | undecided |
| Interface | Streamlit or FastAPI |
| Monitoring | self-hosted logging + Grafana |

If you need to pick one to make progress, say so explicitly and keep the choice behind a thin interface rather than spreading it across `ingest/` and `rag/`.

## Evaluation

`eval/` measures retrieval and generation separately. Beyond the usual retrieval metrics, two project-specific properties are worth testing:

- **Grade fidelity** — does a `weak`-graded retrieval produce a suitably hedged answer, or does the LLM launder it into confidence?
- **Router accuracy** — are knowledge questions and race questions dispatched to the right subsystem? Mixed queries ("what should I run after my first marathon, and what's near me in November?") need both.

## Empty README sections

`README.md` ends with three deliberately empty headings — "Running the project", "Evaluation results", "Monitoring and feedback". Fill these in as the corresponding functionality is built.
