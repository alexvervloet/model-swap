"""The corpus, and the hash that pins a scored run to it.

Documents are written by hand and live under `corpus/meridian/`. This module
loads them, hashes each one, and derives a single version over the set. A run
records that version, so a document edited afterwards invalidates the run
rather than quietly changing what its numbers meant.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from modelswap.sut import repo_root

CORPUS_NAME = "meridian"


def corpus_dir(root: Path | None = None) -> Path:
    """Where the documents live. Only this directory is ever uploaded."""
    return (root or repo_root()) / "corpus" / CORPUS_NAME


@dataclass(frozen=True)
class Document:
    """One document, as the system under test will receive it."""

    doc_id: str
    """Stable identifier, taken from the filename: `04-cancellations-and-refunds`."""

    title: str
    """The first markdown heading, which is what a citation is worth reading as."""

    path: str
    """The path the system under test stores it under."""

    text: str
    digest: str
    """sha256 of the text, so a changed document is visible without a diff."""

    @property
    def words(self) -> int:
        return len(self.text.split())


@dataclass(frozen=True)
class Corpus:
    documents: tuple[Document, ...]
    version: str
    """sha256 over every document id and digest, in order. The run's pin."""

    def __len__(self) -> int:
        return len(self.documents)

    @property
    def words(self) -> int:
        return sum(doc.words for doc in self.documents)

    def by_id(self, doc_id: str) -> Document:
        for doc in self.documents:
            if doc.doc_id == doc_id:
                return doc
        raise KeyError(f"no document {doc_id!r} in corpus {self.version[:12]}")

    def as_items(self) -> list[dict[str, object]]:
        """The shape knowledge-desk's `sync_documents` takes."""
        return [
            {"path": doc.path, "content": doc.text, "acl": ["public-to-org"]}
            for doc in self.documents
        ]


def _title_of(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def load(root: Path | None = None) -> Corpus:
    """Read every document in filename order and pin the set with one hash."""
    directory = corpus_dir(root)
    paths = sorted(directory.glob("*.md"))
    if not paths:
        raise FileNotFoundError(f"no documents found in {directory}")

    documents: list[Document] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        documents.append(
            Document(
                doc_id=path.stem,
                title=_title_of(text, path.stem),
                path=path.name,
                text=text,
                digest=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )

    # Hash the ids alongside the digests: two documents swapping filenames would
    # otherwise leave the version unchanged while every citation moved.
    fingerprint = hashlib.sha256()
    for doc in documents:
        fingerprint.update(doc.doc_id.encode("utf-8"))
        fingerprint.update(doc.digest.encode("utf-8"))

    return Corpus(documents=tuple(documents), version=fingerprint.hexdigest())
