# MaraPal
# Her Marathon — A RAG Q&A System for Women Training for Marathons

## Background

Marathon training material is not scarce on the internet, but the overwhelming majority of training guides, books, and apps take male exercise physiology as their baseline. The questions specific to women runners get very little coverage — how the menstrual cycle affects the scheduling of hard sessions, whether to adjust the plan through period pain, how to return to running postpartum, the risk of amenorrhea and low bone density under sustained high training load (RED-S), women-specific gear choices. What coverage exists is scattered across occasional magazine articles, forum threads, and brand content, so a woman runner has a hard time finding systematic, reliable, source-backed answers in one place.

This project builds a retrieval-augmented generation (RAG) question-answering system covering **every stage of marathon preparation for women**, from absolute beginner through experienced runners chasing a time goal. Users ask in natural language, for example:

- "Which phase of my menstrual cycle is best for hard interval work?"
- "Should I still run long when I have period cramps?"
- "How long after giving birth can I start running again?"
- "Can high mileage disrupt my cycle, and how would I tell?"
- "What shoe last shape suits women's feet?"

The system retrieves relevant material from a curated knowledge base and combines it with general training-science methodology (pacing, periodization) to produce grounded answers with traceable sources.

## Target users and stages covered

All preparation stages, for women runners:
- **Beginner** — building a running habit from zero, training for a first 10K or half marathon
- **Intermediate/advanced** — has finished a half or full marathon, chasing a pace breakthrough
- **Specific physiological phases** — cycle management, pregnancy, and postpartum return to running

## Data sources

| Type | Source | Notes |
|---|---|---|
| Public educational articles | Runner's World, Women's Running, Nike running guides, Oura blog, and similar publicly published brand/organization content | Scraped body text, source URL recorded |
| Community Q&A | Highly-upvoted public answers from running communities (Reddit r/XXRunning, r/AdvancedRunning and similar) on women's marathon training, cycle and running, pregnancy and postpartum running, RED-S | Manually curated excerpts with links to the original, for study and research purposes only |
| Training methodology | Classic running training books (e.g. *Daniels' Running Formula*, Hal Higdon's plans) and women-specific texts (e.g. Stacy Sims' *ROAR*) | **No original text stored.** Read and rewritten by the author into methodology summary entries, with the source reference recorded |

> Copyright note: this repository contains no original book text and no verbatim reproduction of long web articles. Every book-derived knowledge entry is a rewritten summary. To reconstruct the local knowledge base, follow the collection guide in `data/raw/README.md` and gather the material yourself.

## Technical architecture (planned)

- Vector store: TBD (candidates: Qdrant / Elasticsearch)
- Embedding model: TBD (open-source sentence embedding model)
- LLM: TBD
- Interface: Streamlit / FastAPI
- Monitoring: self-hosted logging + Grafana

## Project structure

```
MaraPal/
├── data/
│   ├── raw/          # Collected source material (web snapshots, curated forum answers, book summaries)
│   └── processed/    # Unified jsonl knowledge entries
├── ingest/           # Data ingestion and index building
├── rag/              # Retrieval + prompt construction + LLM call
├── eval/             # Retrieval and generation quality evaluation
├── app/              # Web interface
├── docker/           # Container configuration
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Running the project


## Evaluation results


## Monitoring and feedback

