# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

**This is a pre-implementation scaffold.** As of the initial commit the repo contains only `README.md`, `data/raw/README.md`, and a placeholder `requirements.txt`. Every source directory (`ingest/`, `rag/`, `eval/`, `app/`, `docker/`) is empty, and `docker-compose.yml` is planned but does not exist yet.

There is no build, no test suite, no lint config, and no runnable entrypoint. Do not invent commands for them — when the first real code lands, add the actual commands to this file.

`requirements.txt` is a comment-only stub listing intended dependency *categories*, not pinned packages.

## What this project is

MaraPal (Her Marathon) is a RAG question-answering system about marathon training for women — covering the gaps that male-default training material leaves out: menstrual-cycle-aware training load, pregnancy/postpartum return to running, RED-S and amenorrhea risk, women's gear selection, alongside general periodization and pacing methodology.

Target users span all preparation stages: beginners building a habit toward a first 10K/half, experienced runners chasing pace goals, and runners in specific physiological phases.

## Language convention

Documentation, knowledge-base content, user queries, and generated answers are all **English**. The project was originally scoped in Simplified Chinese and converted to English on 2026-07-30; any leftover Chinese strings, source references, or filenames are stragglers from that conversion — translate them rather than preserving them.

## Copyright constraint — read before touching `data/`

This is the hardest rule in the repo and it shapes the ingest design. Never commit to `data/raw/`:

- Book PDFs or any original book files
- Full chapter text extracted from books
- Verbatim copies of web articles beyond a few sentences of quotation

Book-derived knowledge must exist **only as rewritten summaries** in the author's own words, tagged with a reference to the source book. Web articles are scraped body text stored with their source URL; community Q&A material is manually curated excerpts with links, for study/research purposes only.

Consequence: the repo is not self-contained. A fresh clone cannot rebuild the knowledge base — `data/raw/README.md` holds the collection checklist and instructions for gathering data yourself.

## Architecture

The intended pipeline is a linear data flow, one directory per stage:

```
data/raw/  →  data/processed/  →  ingest/  →  vector store  →  rag/  →  app/
 collected      unified jsonl      chunk +       (TBD)        retrieve +    UI
 sources        entries            index                      prompt + LLM
```

- **`data/raw/`** — heterogeneous collected sources, three planned subdirectories with distinct record shapes: `web_articles/` (body text, filename carries source URL), `community_qa/` (`title`/`content`/`url`/`upvotes`), `book_summaries/` (`topic`/`summary`/`book_ref`).
- **`data/processed/`** — the normalization boundary. Heterogeneous raw records converge into uniform jsonl knowledge entries here; everything downstream reads this format only.
- **`ingest/`** — reads processed jsonl, chunks, embeds, builds the index.
- **`rag/`** — retrieval, prompt construction, LLM call. Answers must be source-attributable, so provenance metadata has to survive every stage from raw through retrieval.
- **`eval/`** — split evaluation: retrieval quality and generation quality are measured separately.
- **`app/`** — web interface.

## Undecided technology choices

Do not assume a stack. The README lists these as open candidates:

| Layer | Candidates |
|---|---|
| Vector store | Qdrant or Elasticsearch |
| Embeddings | an open-source sentence embedding model (undecided) |
| LLM | undecided |
| Interface | Streamlit or FastAPI |
| Monitoring | self-hosted logging + Grafana |

If you need to pick one to make progress, say so explicitly and keep the choice isolated behind a thin interface rather than spreading it across `ingest/` and `rag/`.

## Empty README sections

`README.md` ends with three deliberately empty headings — "Running the project", "Evaluation results", "Monitoring and feedback". Fill these in as the corresponding functionality is built.
