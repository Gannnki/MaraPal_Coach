"""Embed the processed running.wiki chunks for semantic retrieval.

The input is the JSONL produced by ``ingest/wiki.py``. Each output record keeps
all original metadata and adds a normalized ``embedding`` vector. A sidecar
manifest records the model, vector dimension, source checksum and wiki commits
so an index can be reproduced and stale vectors can be detected.

The default model is multilingual because MaraPal's source articles are English
while users may ask questions in German, English or Chinese.

Usage:
    python ingest/embedding.py
    python ingest/embedding.py --device cuda --batch-size 64
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

DEFAULT_INPUT = Path("data/processed/knowledge.jsonl")
DEFAULT_OUTPUT = Path("data/processed/knowledge.embeddings.jsonl")
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def read_records(path: Path) -> list[dict[str, Any]]:
    """Read and validate retrieval records from a JSONL file."""
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    try:
        lines = path.open("r", encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(
            f"knowledge file not found at {path} -- run ingest/wiki.py first"
        ) from None

    with lines:
        for line_number, line in enumerate(lines, start=1):
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
            text = record.get("text")
            if not isinstance(record_id, str) or not record_id.strip():
                raise SystemExit(f"{path}:{line_number}: missing non-empty string 'id'")
            if record_id in seen_ids:
                raise SystemExit(f"{path}:{line_number}: duplicate id {record_id!r}")
            if not isinstance(text, str) or not text.strip():
                raise SystemExit(
                    f"{path}:{line_number}: missing non-empty string 'text'"
                )
            if "embedding" in record:
                raise SystemExit(
                    f"{path}:{line_number}: input already contains an embedding"
                )

            seen_ids.add(record_id)
            records.append(record)

    if not records:
        raise SystemExit(f"no records found in {path}")
    return records


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def batches(items: Sequence[str], size: int) -> Iterator[Sequence[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def load_model(model_name: str, device: str | None):
    """Load sentence-transformers lazily so validation has clear errors."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise SystemExit(
            "sentence-transformers is not installed -- run `uv sync` first"
        ) from None

    try:
        return SentenceTransformer(model_name, device=device)
    except Exception as exc:
        raise SystemExit(f"could not load embedding model {model_name!r}: {exc}") from exc


def encode_records(
    model: Any,
    records: Sequence[dict[str, Any]],
    batch_size: int,
) -> Iterator[tuple[dict[str, Any], list[float]]]:
    """Yield source records paired with normalized finite vectors."""
    try:
        import numpy as np
    except ImportError:
        raise SystemExit("numpy is not installed -- run `uv sync` first") from None

    offset = 0
    texts = [record["text"] for record in records]
    for text_batch in batches(texts, batch_size):
        vectors = model.encode(
            list(text_batch),
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.ndim != 2 or vectors.shape[0] != len(text_batch):
            raise RuntimeError(
                "embedding model returned an unexpected shape "
                f"{tuple(vectors.shape)} for {len(text_batch)} texts"
            )
        if not np.isfinite(vectors).all():
            raise RuntimeError("embedding model returned NaN or infinite values")

        for vector in vectors:
            yield records[offset], vector.tolist()
            offset += 1


def atomic_json_write(path: Path, value: dict[str, Any]) -> None:
    """Write JSON atomically so interrupted runs do not leave valid-looking files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def write_embeddings(
    output: Path,
    encoded: Iterator[tuple[dict[str, Any], list[float]]],
) -> tuple[int, int]:
    """Atomically write embedded JSONL and return (record count, dimension)."""
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        dir=output.parent, prefix=f".{output.name}.", suffix=".tmp"
    )
    count = 0
    dimension: int | None = None
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            for record, vector in encoded:
                if dimension is None:
                    dimension = len(vector)
                    if dimension == 0:
                        raise RuntimeError("embedding model returned an empty vector")
                elif len(vector) != dimension:
                    raise RuntimeError("embedding dimensions are inconsistent")

                output_record = {**record, "embedding": vector}
                stream.write(
                    json.dumps(output_record, ensure_ascii=False, separators=(",", ":"))
                    + "\n"
                )
                count += 1
        os.replace(temporary_name, output)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise

    if dimension is None:
        raise RuntimeError("no embeddings were written")
    return count, dimension


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument(
        "--device",
        default=None,
        help="sentence-transformers device, for example cpu, cuda or mps",
    )
    args = parser.parse_args()

    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    if args.input.resolve() == args.out.resolve():
        parser.error("--input and --out must be different files")

    records = read_records(args.input)
    source_checksum = file_sha256(args.input)
    print(f"loading     {args.model}", flush=True)
    model = load_model(args.model, args.device)
    print(f"embedding   {len(records)} records", flush=True)
    count, dimension = write_embeddings(
        args.out,
        encode_records(model, records, args.batch_size),
    )

    commits = sorted(
        {
            commit
            for record in records
            if isinstance((commit := record.get("wiki_commit")), str) and commit
        }
    )
    manifest_path = args.out.with_suffix(args.out.suffix + ".meta.json")
    atomic_json_write(
        manifest_path,
        {
            "format_version": 1,
            "model": args.model,
            "dimension": dimension,
            "normalized": True,
            "record_count": count,
            "source": str(args.input),
            "source_sha256": source_checksum,
            "wiki_commits": commits,
        },
    )

    print(f"model       {args.model}")
    print(f"records     {count}")
    print(f"dimension   {dimension}")
    print(f"wrote       {args.out}")
    print(f"manifest    {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
