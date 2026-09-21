# CLAUDE.md

Guidance for Claude Code when working in this repository.

MaraPal Coach is a chatbot with two jobs: answer running-training questions from
[running.wiki](https://running.wiki) (RAG), and list **German** running events
(exact filters over SQLite). It is an LLM Zoomcamp course project, not production.

## Tech stack

- **Language / tooling:** Python 3.13 (`>=3.11`), `uv` for dependencies (`uv.lock` is committed).
- **Orchestration:** LangGraph (router → knowledge / races / mixed), LangChain, LangSmith tracing (opt-in).
- **Storage:** ChromaDB for knowledge prose, SQLite for race events and monitoring.
- **Retrieval:** vector (default, best on the eval set), BM25 (`rank-bm25`) and hybrid RRF; switch with `MARAPAL_RETRIEVAL_MODE` or `marapal ask --retrieval-mode`.
- **Models:** OpenAI `gpt-4.1-mini` (chat) and `text-embedding-3-small` (embeddings).
- **Serving:** FastAPI + uvicorn backend, Streamlit frontend, Docker Compose.
- **Ingestion schedule:** Kestra (backed by Postgres), weekly, Mondays 04:00 Europe/Berlin.
- **Dev / eval:** pytest, DeepEval GEval with a Gemini judge.

## Project structure

| Path | Purpose |
|---|---|
| `main.py` | CLI (`marapal`): `index`, `import-races`, `ask` |
| `rag/` | Core logic, no web framework: `graph.py` (LangGraph), `knowledge.py` (Chroma, prompts, citation check), `retrieval.py`, `races.py` (SQLite schema, `RaceFilters`, search), `style.py`, `monitoring.py`, `config.py` (all settings) |
| `app/` | `api.py` (FastAPI: `/api/v1/ask`, `/feedback`, `/validate-key`, `/monitoring`), `streamlit_app.py` (UI, talks to the API over HTTP), `monitoring_page.py`, `pages/` |
| `ingest/` | Offline scripts that write JSONL: `wiki.py` (running.wiki chunks), `dlv_calendar.py` (DLV race calendar, stdlib only) |
| `eval/` | Retrieval and generation evaluation plus their datasets |
| `tests/` | Offline pytest suite |
| `kestra/ingestion.yml` | Weekly ingestion flow |
| `docker/`, `docker-compose.yaml` | Images and stack: `api`, `streamlit`, `postgres`, `kestra` |
| `deploy/` | systemd unit for the ngrok demo tunnel |
| `data/` | `raw/README.md` (source notes) is tracked; `raw/running-wiki`, `raw/races`, `processed/`, `vector/` are gitignored |

## Running the project

### Environment (`.env`, copy from `.env.example`)

| Variable | Needed for |
|---|---|
| `OPENAI_API_KEY` | Building the Chroma index and evals. App users enter their own key in the Streamlit sidebar; the API reads it from the `X-OpenAI-API-Key` header and never stores it |
| `KESTRA_DB_USER`, `KESTRA_DB_PASSWORD`, `KESTRA_DB_NAME` | Postgres and Kestra. **Compose refuses to start any service if these are empty** |
| `KESTRA_SECRET_OPENAI_API_KEY` | Base64 of the OpenAI key, exposed to Kestra. Also required by Compose |
| `GOOGLE_API_KEY` | Generation eval (Gemini judge) only |
| `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` | Optional tracing; off by default |
| `MARAPAL_*` | Optional overrides of paths, models, retrieval mode (see `rag/config.py`) |

### Docker Compose

```bash
git clone https://github.com/jacquescorbytuech/running-knowledge-base data/raw/running-wiki
cp .env.example .env            # then fill it in

docker compose build api
# One-time data setup. Use `python main.py`, not `marapal`: the console script
# fails inside the container with "No module named 'rag'".
docker compose run --rm api python ingest/wiki.py --wiki data/raw/running-wiki --out /data/processed/knowledge.jsonl
docker compose run --rm api python main.py index --input /data/processed/knowledge.jsonl
docker compose run --rm api python ingest/dlv_calendar.py --out /data/processed/races.jsonl
docker compose run --rm api python main.py import-races /data/processed/races.jsonl

docker compose up -d --build    # start everything
docker compose ps
docker compose down             # stop
```

| Service | URL |
|---|---|
| Streamlit | http://localhost:8501 |
| API and docs | http://localhost:8000/docs |
| Monitoring | http://localhost:8000/monitoring |
| Kestra | http://localhost:8080 |

Images copy the code at build time. After editing code, rebuild (`docker compose up -d --build`)
before running scripts through `docker compose run`. If a port is taken, change the host side in
`docker-compose.yaml`.

### Without Docker

```bash
uv sync
uv run uvicorn app.api:app --port 8000
uv run streamlit run app/streamlit_app.py     # MARAPAL_API_URL defaults to http://localhost:8000
uv run marapal ask "Show me five half marathons in Bayern."
```

## Tests

```bash
uv sync --dev                # pytest, deepeval and friends live in the dev group
uv run pytest -q             # full suite; offline, no OpenAI / Gemini / LangSmith calls
uv run pytest tests/test_dlv_calendar.py -q   # one file
```

CI (`.github/workflows/ci.yml`) runs `uv sync --locked --dev` and `uv run pytest -q`, then builds both images.

Evaluations call paid APIs and are not part of the suite:

```bash
uv run python -m eval.retrieval                 # needs OPENAI_API_KEY
uv run python -m eval.generation --limit 3      # needs OPENAI_API_KEY and GOOGLE_API_KEY
```

## Design rules

- **Two subsystems, never mixed.** Knowledge is prose in ChromaDB (semantic search). Race events are
  time-sensitive structured records in SQLite (exact filters). Never put race records in ChromaDB.
  The LLM only extracts `RaceFilters`; a fixed SQL query does the search.
- **Never infer registration status from the date.** The DLV calendar has none, so ingestion writes
  `unknown`. A future date does not mean entry is open (it may be sold out). When status is `unknown`,
  say so and give the link and last-checked time. Ladder: `not_yet_open` / `open` / `late_only` /
  `sold_out` / `closed` / `unknown`. Resolve status lazily per asked event, not by crawling.
- **Freshness is correctness.** Every race record carries `fetched_at`. `ingest/dlv_calendar.py` uses an
  undocumented laufen.de endpoint that has already moved once; it fails loudly and warns when the
  parsed count differs from the site's `total`.
- **Germany only.** No US race sources. Do not ingest runme.de: its `robots.txt` blocks AI crawlers.
  Source assessment is in `data/raw/README.md`.
- **Keep the evidence grade and citations.** running.wiki grades claims (`strong` / `moderate` /
  `limited` / `weak` / `contested`). The grade must reach the prompt and the answer; weak evidence must
  be hedged. Resolve relative `sources/` links at ingest time. Skip `index.md` files.
- **Upstream wiki:** clone it, never scrape. Pin the commit SHA in processed output.
- **Non-commercial.** No product recommendations or affiliate links. Health, injury and nutrition answers
  end with a "Not medical advice" note. Credit running.wiki (MIT) in answers.
- **Provider and storage choices live in `rag/config.py`.**
- **Never store or trace the user's OpenAI key.** It is injected into the provider clients per request only.
