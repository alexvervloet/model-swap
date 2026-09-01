"""Validation is the point of this module: a malformed question set should fail
at load rather than halfway through a paid run."""

from __future__ import annotations

from pathlib import Path

import pytest

from modelswap import corpus, questions


def _corpus(root: Path, *doc_ids: str) -> None:
    directory = corpus.corpus_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    for doc_id in doc_ids:
        (directory / f"{doc_id}.md").write_text(f"# {doc_id}\n\nbody\n", encoding="utf-8")


def _questions(root: Path, name: str, body: str) -> None:
    directory = questions.questions_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(body, encoding="utf-8")


def test_stratum_comes_from_the_filename(tmp_path: Path) -> None:
    _corpus(tmp_path, "01-fleet")
    _questions(
        tmp_path,
        "01-single.toml",
        '[[question]]\nid = "a"\ntext = "t"\nexpect = "answerable"\nsources = ["01-fleet"]\n',
    )
    loaded = questions.load(tmp_path)
    assert loaded.questions[0].stratum == "single"


def test_a_source_outside_the_corpus_is_an_error(tmp_path: Path) -> None:
    """The failure this prevents: a renamed document silently orphaning the
    questions that pointed at it, discovered during a scored run."""
    _corpus(tmp_path, "01-fleet")
    _questions(
        tmp_path,
        "01-single.toml",
        '[[question]]\nid = "a"\ntext = "t"\nexpect = "answerable"\nsources = ["99-ghost"]\n',
    )
    with pytest.raises(questions.QuestionSetError, match="99-ghost"):
        questions.load(tmp_path)


def test_an_answerable_question_must_name_a_source(tmp_path: Path) -> None:
    _corpus(tmp_path, "01-fleet")
    _questions(
        tmp_path, "01-single.toml", '[[question]]\nid = "a"\ntext = "t"\nexpect = "answerable"\n'
    )
    with pytest.raises(questions.QuestionSetError, match="must name its sources"):
        questions.load(tmp_path)


def test_a_refusal_question_cannot_have_sources(tmp_path: Path) -> None:
    """A refusal with a source is a contradiction: the source is what would
    make it answerable."""
    _corpus(tmp_path, "01-fleet")
    _questions(
        tmp_path,
        "04-refusal.toml",
        '[[question]]\nid = "a"\ntext = "t"\nexpect = "refusal"\nsources = ["01-fleet"]\n',
    )
    with pytest.raises(questions.QuestionSetError, match="cannot have sources"):
        questions.load(tmp_path)


def test_an_unknown_expectation_is_an_error(tmp_path: Path) -> None:
    _corpus(tmp_path, "01-fleet")
    _questions(tmp_path, "01-single.toml", '[[question]]\nid = "a"\ntext = "t"\nexpect = "maybe"\n')
    with pytest.raises(questions.QuestionSetError, match="expect must be"):
        questions.load(tmp_path)


def test_duplicate_ids_are_refused_across_files(tmp_path: Path) -> None:
    _corpus(tmp_path, "01-fleet")
    entry = '[[question]]\nid = "same"\ntext = "t"\nexpect = "refusal"\n'
    _questions(tmp_path, "01-single.toml", entry)
    _questions(tmp_path, "04-refusal.toml", entry)
    with pytest.raises(questions.QuestionSetError, match="duplicate question ids"):
        questions.load(tmp_path)


def test_editing_a_question_moves_the_version(tmp_path: Path) -> None:
    _corpus(tmp_path, "01-fleet")
    _questions(
        tmp_path, "01-single.toml", '[[question]]\nid = "a"\ntext = "t"\nexpect = "refusal"\n'
    )
    before = questions.load(tmp_path).version

    _questions(
        tmp_path, "01-single.toml", '[[question]]\nid = "a"\ntext = "t2"\nexpect = "refusal"\n'
    )

    assert questions.load(tmp_path).version != before


# The real set.


def test_the_real_set_is_balanced() -> None:
    loaded = questions.load()
    assert len(loaded) == 120
    assert set(loaded.strata) == {
        "single",
        "multihop",
        "override",
        "refusal",
        "nearmiss",
        "unflattering",
    }
    assert all(count == 20 for count in loaded.strata.values())


def test_every_question_explains_why_it_exists() -> None:
    """A question with no note is one nobody can review. The notes are where
    the expected answer lives, so a scored run can be argued with."""
    unexplained = [q.qid for q in questions.load().questions if not q.notes.strip()]
    assert unexplained == []
