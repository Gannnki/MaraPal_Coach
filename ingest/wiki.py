"""Turn the running.wiki markdown bundle into retrieval-ready chunks.

Two passes, because content pages cite source pages and we want the citation
resolved at ingest time rather than at query time:

  1. Index sources/ -- 619 pages, each an anchor to one paper or consensus
     statement, carrying the link to the primary material in `resource:`.
  2. Walk the content pages, split each into sections, and attach both the
     page's frontmatter and its resolved citations to every chunk.

The `evidence` grade is the reason this knowledge base is worth using, so it
rides on every chunk. A chunk that reaches the prompt without its grade reads as
confident regardless of how thin the underlying support is.

Usage:
    python ingest/wiki.py --wiki data/raw/running-wiki --out data/processed/knowledge.jsonl
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import subprocess
from pathlib import Path

import yaml

SITE = "https://running.wiki"

# Navigation and repo scaffolding, not knowledge. index.md files are tables of
# contents: they would retrieve well (dense with keywords) and answer nothing.
SKIP_NAMES = {"index.md", "README.md", "CONTRIBUTING.md", "CLAUDE.md", "log.md"}

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.S)
H1_RE = re.compile(r"^#\s+.*$", re.M)
SECTION_RE = re.compile(r"^##\s+(.*)$", re.M)
LINK_RE = re.compile(
    r"\[([^\]]+)\]\((?!https?://|mailto:|#)([^)\s]+\.md)(?:#[^)]*)?\)"
)

# Sections shorter than this get folded into the previous one. A 20-word chunk
# retrieves badly: too little signal to match, too little content to answer.
MIN_SECTION_WORDS = 40
# Stay comfortably below the input limit of common embedding models after the
# title and section are prepended. Paragraph boundaries remain the first choice.
MAX_CHUNK_WORDS = 350


def repo_commit(wiki: Path) -> str:
    """Pin every record to the upstream commit it came from."""
    try:
        out = subprocess.run(
            ["git", "-C", str(wiki), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return YAML metadata and the remaining markdown.

    Most upstream frontmatter is valid YAML, but a source title can contain an
    unquoted ``": "`` (for example ``title: Alcohol: impact ...``). YAML reads
    that as the start of a nested mapping and rejects the whole document. These
    files still follow the wiki's simple one-key-per-line schema, so fall back
    to parsing that schema rather than making one bibliography typo abort the
    complete ingest.
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    raw = m.group(1)
    try:
        metadata = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        metadata = {}
        for line in raw.splitlines():
            if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
                continue
            key, value = line.split(":", 1)
            key, value = key.strip(), value.strip()
            if value.startswith(("[", "{", "'", '"')):
                try:
                    metadata[key] = yaml.safe_load(value)
                    continue
                except yaml.YAMLError:
                    pass
            metadata[key] = value
    if not isinstance(metadata, dict):
        raise ValueError("frontmatter must be a YAML mapping")
    return metadata, text[m.end():]


def page_url(rel: str) -> str:
    """'concepts/lactate-threshold.md' -> 'https://running.wiki/concepts/lactate-threshold'"""
    return f"{SITE}/{rel[:-3] if rel.endswith('.md') else rel}"


def resolve(href: str, from_dir: str) -> str:
    """Resolve a relative markdown link to a repo-root-relative path.

    Links are either same-directory ('vo2max.md') or parent-relative
    ('../sources/coyle-1995.md'). Left unresolved they are dead the moment the
    text leaves the repo, which is most of the point of doing this at all.
    """
    return posixpath.normpath(posixpath.join(from_dir, href))


def index_sources(wiki: Path) -> dict[str, dict]:
    """Map 'sources/foo.md' -> {title, resource} for citation resolution."""
    index = {}
    for path in sorted((wiki / "sources").glob("*.md")):
        if path.name in SKIP_NAMES:
            continue
        fm, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        rel = f"sources/{path.name}"
        index[rel] = {
            "title": fm.get("title", path.stem),
            "resource": fm.get("resource"),   # link to the primary paper
            "wiki_url": page_url(rel),
        }
    return index


def split_sections(body: str) -> list[tuple[str, str]]:
    """Split a page into (heading, text). The lead paragraph gets heading ''."""
    body = H1_RE.sub("", body, count=1).strip()
    marks = list(SECTION_RE.finditer(body))

    sections: list[tuple[str, str]] = []
    lead = body[: marks[0].start()] if marks else body
    if lead.strip():
        sections.append(("", lead.strip()))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        text = body[m.end():end].strip()
        if text:
            sections.append((m.group(1).strip(), text))

    # Fold short sections into the previous one rather than emit thin chunks.
    merged: list[tuple[str, str]] = []
    for heading, text in sections:
        if merged and len(text.split()) < MIN_SECTION_WORDS:
            prev_h, prev_t = merged[-1]
            merged[-1] = (prev_h, f"{prev_t}\n\n## {heading}\n\n{text}" if heading else f"{prev_t}\n\n{text}")
        else:
            merged.append((heading, text))
    return merged


def split_long_text(text: str, max_words: int = MAX_CHUNK_WORDS) -> list[str]:
    """Split long section text on paragraphs, then sentences when necessary."""
    if len(text.split()) <= max_words:
        return [text]

    units: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph.split()) <= max_words:
            units.append(paragraph)
            continue

        # Prose paragraphs are rare in the wiki at this size, but splitting one
        # prevents a single paragraph from defeating the chunk limit.
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9`\[])|(?<=\.)\s+(?=>)", paragraph)
        units.extend(sentence.strip() for sentence in sentences if sentence.strip())

    chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    for unit in units:
        words = unit.split()
        hard_split = False
        # A sentence can itself exceed the limit. Hard splitting is preferable
        # to silent truncation, even though this should almost never be needed.
        while len(words) > max_words:
            hard_split = True
            if current:
                chunks.append("\n\n".join(current))
                current, current_words = [], 0
            chunks.append(" ".join(words[:max_words]))
            words = words[max_words:]
        if not words:
            continue
        if current and current_words + len(words) > max_words:
            chunks.append("\n\n".join(current))
            current, current_words = [], 0
        current.append(" ".join(words) if hard_split else unit)
        current_words += len(words)
    if current:
        chunks.append("\n\n".join(current))

    # Avoid a tiny trailing chunk by folding it back when that stays reasonably
    # close to the target. Retrieval benefits more from context than a hard cap.
    if len(chunks) > 1 and len(chunks[-1].split()) < MIN_SECTION_WORDS:
        chunks[-2] = f"{chunks[-2]}\n\n{chunks[-1]}"
        chunks.pop()
    return chunks


def unique_links(links: list[dict], key: str) -> list[dict]:
    """Preserve document order while removing repeated link targets."""
    seen = set()
    unique = []
    for link in links:
        if link[key] not in seen:
            seen.add(link[key])
            unique.append(link)
    return unique


def chunk_page(path: Path, wiki: Path, sources: dict, commit: str) -> list[dict]:
    rel = path.relative_to(wiki).as_posix()
    from_dir = rel.rsplit("/", 1)[0] if "/" in rel else ""
    fm, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    title = fm.get("title", path.stem)

    chunks = []
    for heading, section_text in split_sections(body):
        for part, text in enumerate(split_long_text(section_text), start=1):
            citations, cross_links = [], []
            for label, href in LINK_RE.findall(text):
                target = resolve(href, from_dir)
                if target in sources:
                    citations.append({"label": label, **sources[target]})
                else:
                    cross_links.append({"label": label, "url": page_url(target)})

            citations = unique_links(citations, "wiki_url")
            cross_links = unique_links(cross_links, "url")
            slug = heading.lower().replace(" ", "-") or "lead"
            if part > 1:
                slug = f"{slug}-{part}"
            chunks.append({
                "id": f"{rel[:-3]}#{slug}",
                "page": rel[:-3],
                "title": title,
                "section": heading,
                # What gets embedded. Title and section restore the context the
                # split removed; without them "It is a fuel, not a waste product"
                # is unmatchable. The evidence grade is deliberately NOT in here --
                # it must not influence semantic similarity, only the answer.
                "text": f"{title} — {heading}\n\n{text}" if heading else f"{title}\n\n{text}",
                "type": fm.get("type"),
                "description": fm.get("description"),
                "tags": fm.get("tags", []),
                # None for the ~20 Event and editorial pages that carry no grade.
                # Do not default this to a value; an absent grade is not a weak one.
                "evidence": fm.get("evidence"),
                "timestamp": str(fm.get("timestamp", "")),
                "url": page_url(rel),
                "citations": citations,
                "cross_links": cross_links,
                "word_count": len(text.split()),
                "wiki_commit": commit,
            })
    return chunks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wiki", type=Path, default=Path("data/raw/running-wiki"))
    ap.add_argument("--out", type=Path, default=Path("data/processed/knowledge.jsonl"))
    args = ap.parse_args()

    if not args.wiki.exists():
        raise SystemExit(f"wiki bundle not found at {args.wiki} -- run ingest/clone_wiki.sh first")

    commit = repo_commit(args.wiki)
    sources = index_sources(args.wiki)

    pages = [
        p for p in sorted(args.wiki.rglob("*.md"))
        if p.name not in SKIP_NAMES
        and p.relative_to(args.wiki).parts[0] != "sources"
        and not p.relative_to(args.wiki).parts[0].startswith(".")
    ]

    chunks = [c for p in pages for c in chunk_page(p, args.wiki, sources, commit)]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for c in chunks:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    graded = sum(1 for c in chunks if c["evidence"])
    cited = sum(1 for c in chunks if c["citations"])
    print(f"wiki commit    {commit[:12]}")
    print(f"source index   {len(sources)} pages")
    print(f"content pages  {len(pages)}")
    print(f"chunks         {len(chunks)}  ({graded} graded, {cited} with citations)")
    print(f"wrote          {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
