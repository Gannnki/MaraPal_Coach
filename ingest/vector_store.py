"""Load embedded knowledge chunks into a Qdrant vector database.

By default Qdrant runs in local persistent mode, which needs no server:

    python ingest/vector_store.py

For a Qdrant server or Cloud deployment:

    python ingest/vector_store.py --url http://localhost:6333

Point IDs are deterministic UUIDs derived from the wiki chunk IDs, so rerunning
the command updates existing points instead of creating duplicates. All fields
except ``embedding`` become Qdrant payload available to retrieval and filters.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

DEFAULT_INPUT = Path("data/processed/knowledge.embeddings.jsonl")
DEFAULT_PATH = Path("data/vector/qdrant")
DEFAULT_COLLECTION = "running_knowledge"
POINT_NAMESPACE = uuid.UUID("c9eb15a2-29f8-5e34-8614-3b421d5ad8a2")


def load_qdrant():
    try:
        from qdrant_client import QdrantClient, models
    except ImportError:
        raise SystemExit("qdrant-client is not installed -- run `uv sync` first") from None
    return QdrantClient, models


def read_embedded(path: Path) -> Iterator[tuple[str, list[float], dict[str, Any]]]:
    """Yield validated (record ID, vector, payload) tuples."""
    try:
        stream = path.open("r", encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(
            f"embedding file not found at {path} -- run ingest/embedding.py first"
        ) from None

    seen_ids: set[str] = set()
    dimension: int | None = None
    with stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(
                    f"{path}:{line_number}: invalid JSON: {exc.msg}"
                ) from exc
            if not isinstance(record, dict):
                raise SystemExit(f"{path}:{line_number}: record must be an object")

            record_id = record.get("id")
            vector = record.get("embedding")
            if not isinstance(record_id, str) or not record_id:
                raise SystemExit(f"{path}:{line_number}: missing string 'id'")
            if record_id in seen_ids:
                raise SystemExit(f"{path}:{line_number}: duplicate id {record_id!r}")
            if (
                not isinstance(vector, list)
                or not vector
                or any(
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(value)
                    for value in vector
                )
            ):
                raise SystemExit(
                    f"{path}:{line_number}: 'embedding' must be a numeric array"
                )
            if dimension is None:
                dimension = len(vector)
            elif len(vector) != dimension:
                raise SystemExit(
                    f"{path}:{line_number}: expected dimension {dimension}, "
                    f"got {len(vector)}"
                )

            seen_ids.add(record_id)
            payload = {key: value for key, value in record.items() if key != "embedding"}
            yield record_id, vector, payload


def vector_size(collection_info: Any) -> int | None:
    """Extract the size of an unnamed dense vector from Qdrant's response."""
    vectors = collection_info.config.params.vectors
    size = getattr(vectors, "size", None)
    return int(size) if size is not None else None


def ensure_collection(
    client: Any,
    models: Any,
    collection: str,
    dimension: int,
) -> None:
    if not client.collection_exists(collection):
        client.create_collection(
            collection_name=collection,
            vectors_config=models.VectorParams(
                size=dimension,
                distance=models.Distance.COSINE,
            ),
        )
        return

    existing_size = vector_size(client.get_collection(collection))
    if existing_size is not None and existing_size != dimension:
        raise SystemExit(
            f"collection {collection!r} has dimension {existing_size}, "
            f"but input vectors have dimension {dimension}; use a new collection name"
        )


def connect(url: str | None, path: Path, api_key: str | None):
    QdrantClient, models = load_qdrant()
    if url:
        return QdrantClient(url=url, api_key=api_key), models
    path.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=str(path)), models


def upload(
    client: Any,
    models: Any,
    collection: str,
    records: Iterator[tuple[str, list[float], dict[str, Any]]],
    batch_size: int,
) -> int:
    """Create the collection when needed and upsert all records."""
    try:
        first = next(records)
    except StopIteration:
        raise SystemExit("embedding input contains no records") from None

    ensure_collection(client, models, collection, len(first[1]))

    def points():
        for record_id, vector, payload in _prepend(first, records):
            yield models.PointStruct(
                id=str(uuid.uuid5(POINT_NAMESPACE, record_id)),
                vector=vector,
                payload=payload,
            )

    client.upload_points(
        collection_name=collection,
        points=points(),
        batch_size=batch_size,
        parallel=1,
        wait=True,
    )
    return client.count(collection_name=collection, exact=True).count


def _prepend(first: Any, rest: Iterator[Any]) -> Iterator[Any]:
    yield first
    yield from rest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--url", help="Qdrant URL; when set, --path is ignored")
    parser.add_argument(
        "--api-key-env",
        default="QDRANT_API_KEY",
        help="environment variable containing the Qdrant API key",
    )
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    if not args.collection.strip():
        parser.error("--collection must not be empty")

    api_key = os.environ.get(args.api_key_env) if args.url else None
    client, models = connect(args.url, args.path, api_key)
    try:
        count = upload(
            client,
            models,
            args.collection,
            read_embedded(args.input),
            args.batch_size,
        )
    finally:
        client.close()

    location = args.url or str(args.path)
    print(f"collection   {args.collection}")
    print(f"points       {count}")
    print(f"qdrant       {location}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
