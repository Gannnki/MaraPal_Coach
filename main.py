"""Command-line entry point for indexing data and querying MaraPal."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(prog="marapal")
    commands = parser.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index", help="index processed wiki chunks in Chroma")
    index.add_argument("--input", type=Path, default=Path("data/processed/knowledge.jsonl"))
    races = commands.add_parser("import-races", help="load a DLV JSONL snapshot into SQLite")
    races.add_argument("input", type=Path)
    ask = commands.add_parser("ask", help="ask a running or German race question")
    ask.add_argument("question")
    ask.add_argument("--retrieval-mode", choices=("bm25", "vector", "hybrid"), default=None)
    args = parser.parse_args()

    from rag.config import Settings
    settings = Settings.from_env()
    if args.command == "index":
        from rag.knowledge import index_documents, load_documents, vector_store
        count = index_documents(vector_store(settings), load_documents(args.input))
        print(f"Indexed {count} chunks in {settings.chroma_path}")
    elif args.command == "import-races":
        from rag.races import connect, import_jsonl
        with connect(settings.race_db) as connection:
            count = import_jsonl(connection, args.input)
        print(f"Imported {count} races into {settings.race_db}")
    else:
        from rag.graph import build_graph
        result = build_graph(settings, retrieval_mode=args.retrieval_mode).invoke(
            {"question": args.question},
            config={"run_name": "marapal-question", "tags": ["cli"]},
        )
        print(result["answer"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
