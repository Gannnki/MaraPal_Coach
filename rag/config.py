"""Runtime configuration, kept in one place for easy provider changes."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Local development reads .env automatically. Existing shell/hosting environment
# variables keep precedence because python-dotenv defaults to override=False.
load_dotenv()


@dataclass(frozen=True)
class Settings:
    chat_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    chroma_path: Path = Path("data/vector/chroma")
    chroma_collection: str = "running_knowledge"
    race_db: Path = Path("data/processed/races.sqlite3")
    monitoring_db: Path = Path("data/processed/monitoring.sqlite3")
    knowledge_path: Path = Path("data/processed/knowledge.jsonl")
    retrieval_mode: str = "vector"
    retrieval_k: int = 5

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            chat_model=os.getenv("MARAPAL_CHAT_MODEL", cls.chat_model),
            embedding_model=os.getenv(
                "MARAPAL_EMBEDDING_MODEL", cls.embedding_model
            ),
            chroma_path=Path(os.getenv("MARAPAL_CHROMA_PATH", str(cls.chroma_path))),
            chroma_collection=os.getenv(
                "MARAPAL_CHROMA_COLLECTION", cls.chroma_collection
            ),
            race_db=Path(os.getenv("MARAPAL_RACE_DB", str(cls.race_db))),
            monitoring_db=Path(
                os.getenv("MARAPAL_MONITORING_DB", str(cls.monitoring_db))
            ),
            knowledge_path=Path(os.getenv("MARAPAL_KNOWLEDGE_PATH", str(cls.knowledge_path))),
            retrieval_mode=os.getenv("MARAPAL_RETRIEVAL_MODE", cls.retrieval_mode),
            retrieval_k=int(os.getenv("MARAPAL_RETRIEVAL_K", cls.retrieval_k)),
        )
