"""Two kinds of test here: the loader's behaviour, on corpora built in tmp_path,
and a handful of assertions about the real corpus that encode what LESSONS
entry 2 cost to learn.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modelswap import corpus


def _write(root: Path, name: str, text: str) -> None:
    directory = corpus.corpus_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(text, encoding="utf-8")


def test_loads_documents_in_filename_order(tmp_path: Path) -> None:
    _write(tmp_path, "02-second.md", "# Second\n\nbody\n")
    _write(tmp_path, "01-first.md", "# First\n\nbody\n")

    loaded = corpus.load(tmp_path)

    assert [d.doc_id for d in loaded.documents] == ["01-first", "02-second"]
    assert [d.title for d in loaded.documents] == ["First", "Second"]


def test_an_empty_corpus_is_an_error_rather_than_an_empty_run(tmp_path: Path) -> None:
    corpus.corpus_dir(tmp_path).mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        corpus.load(tmp_path)


def test_editing_a_document_moves_the_version(tmp_path: Path) -> None:
    _write(tmp_path, "01-first.md", "# First\n\nbody\n")
    before = corpus.load(tmp_path).version

    _write(tmp_path, "01-first.md", "# First\n\nbody, amended\n")

    assert corpus.load(tmp_path).version != before


def test_swapping_two_filenames_moves_the_version(tmp_path: Path) -> None:
    """Hashing content alone would miss this, and every citation would have
    moved to a different document while the run claimed to be comparable."""
    _write(tmp_path, "01-a.md", "# A\n\nalpha\n")
    _write(tmp_path, "02-b.md", "# B\n\nbeta\n")
    before = corpus.load(tmp_path).version

    _write(tmp_path, "01-a.md", "# B\n\nbeta\n")
    _write(tmp_path, "02-b.md", "# A\n\nalpha\n")

    assert corpus.load(tmp_path).version != before


def test_a_document_without_a_heading_falls_back_to_its_id(tmp_path: Path) -> None:
    _write(tmp_path, "01-untitled.md", "no heading here\n")
    assert corpus.load(tmp_path).documents[0].title == "01-untitled"


def test_by_id_names_the_corpus_when_it_misses(tmp_path: Path) -> None:
    _write(tmp_path, "01-first.md", "# First\n\nbody\n")
    loaded = corpus.load(tmp_path)
    with pytest.raises(KeyError, match="02-nope"):
        loaded.by_id("02-nope")


def test_items_carry_the_org_wide_acl(tmp_path: Path) -> None:
    _write(tmp_path, "01-first.md", "# First\n\nbody\n")
    items = corpus.load(tmp_path).as_items()
    assert items == [
        {"path": "01-first.md", "content": "# First\n\nbody\n", "acl": ["public-to-org"]}
    ]


# The real corpus. These are the properties that make it measurable at all.


def test_the_real_corpus_loads() -> None:
    assert len(corpus.load()) >= 13


def test_every_document_is_long_enough_to_ask_something_hard_about() -> None:
    """The system under test shipped with four one-sentence documents, over
    which every question is either trivial or impossible. 150 words is not a
    quality bar, it is the floor below which a document cannot separate a
    strong candidate from a weak one."""
    thin = [(d.doc_id, d.words) for d in corpus.load().documents if d.words < 150]
    assert thin == []


def test_every_document_has_a_title() -> None:
    untitled = [d.doc_id for d in corpus.load().documents if d.title == d.doc_id]
    assert untitled == []
