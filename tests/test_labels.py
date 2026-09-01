"""The calibration set has to be the same every round, on every machine, and a
labeling session has to survive being interrupted."""

from __future__ import annotations

from pathlib import Path

from modelswap import answers, corpus, judge, labels, questions
from modelswap.sut import repo_root


def _workspace(tmp_path: Path) -> Path:
    """A repo root whose corpus and questions are the real ones, and whose
    cache and labels are throwaway.

    `root` means repo root everywhere in this project, so a test that wants the
    real question set and a temporary output directory has to build one.
    """
    (tmp_path / "corpus").symlink_to(repo_root() / "corpus")
    (tmp_path / "questions").symlink_to(repo_root() / "questions")
    return tmp_path


def _label(**overrides: object) -> labels.Label:
    fields: dict[str, object] = {
        "qid": "q1",
        "variant": "claude-sonnet-5",
        "sample": 0,
        "answer_digest": judge.digest("an answer"),
        "correct": True,
        "behaviour": "answered",
        "round": 1,
        "labeled_at": "2026-09-01T00:00:00+00:00",
    }
    fields.update(overrides)
    return labels.Label(**fields)  # type: ignore[arg-type]


def _type(monkeypatch, replies: list[str]) -> None:
    """Answer the next prompts in order. `input` takes the prompt string, so a
    bare iterator's `__next__` will not do."""
    supply = iter(replies)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(supply))


def _seed_answer(root: Path, question: questions.Question, variant: str, text: str) -> None:
    answers.write_cached(
        answers.Answer(
            qid=question.qid,
            variant=variant,
            sample=0,
            question=question.text,
            text=text,
            sources=[],
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
            seconds=0.1,
            corpus_version=corpus.load().version,
        ),
        root,
    )


# --- the calibration set ---------------------------------------------------


def test_the_calibration_set_is_stable_across_calls() -> None:
    first = [(q.qid, v) for q, v in labels.calibration_set()]
    second = [(q.qid, v) for q, v in labels.calibration_set()]
    assert first == second


def test_the_calibration_set_is_stratified() -> None:
    """Not a random sample of the whole set: a judge that agrees on lookups
    while missing every refusal would average out to something that looks
    fine."""
    counts: dict[str, int] = {}
    for question, _ in labels.calibration_set():
        counts[question.stratum] = counts.get(question.stratum, 0) + 1

    assert len(counts) == 6
    assert all(count == labels.PER_STRATUM for count in counts.values())


def test_both_models_appear_in_every_stratum() -> None:
    """A calibration set from the strongest model alone is 41 correct answers
    out of 42: the human and the judge agree on everything, kappa is undefined,
    and the floor refuses to certify a judge nobody tested. The spread is the
    point, and it has to be present in each stratum rather than only overall."""
    seen: dict[str, set[str]] = {}
    for question, variant in labels.calibration_set():
        seen.setdefault(question.stratum, set()).add(variant)

    assert len(seen) == 6
    for stratum, variants in seen.items():
        assert variants == set(labels.CALIBRATION_VARIANTS), stratum


def test_each_question_is_labeled_once() -> None:
    """Two rounds of 42 is already slow. Two rounds of 84 does not get done."""
    qids = [question.qid for question, _ in labels.calibration_set()]
    assert len(qids) == len(set(qids)) == 42


# --- storage ---------------------------------------------------------------


def test_labels_append_and_read_back(tmp_path: Path) -> None:
    labels.append_label(_label(), tmp_path)
    labels.append_label(_label(qid="q2", correct=False), tmp_path)

    read = labels.read_labels(1, tmp_path)
    assert [entry.qid for entry in read] == ["q1", "q2"]
    assert [entry.correct for entry in read] == [True, False]


def test_rounds_are_kept_apart(tmp_path: Path) -> None:
    """Round 2 must not be able to see round 1, and the simplest guarantee is
    that it never reads the same file."""
    labels.append_label(_label(correct=True, round=1), tmp_path)
    labels.append_label(_label(correct=False, round=2), tmp_path)

    assert [entry.correct for entry in labels.read_labels(1, tmp_path)] == [True]
    assert [entry.correct for entry in labels.read_labels(2, tmp_path)] == [False]


def test_no_labels_reads_as_empty_rather_than_failing(tmp_path: Path) -> None:
    assert labels.read_labels(1, tmp_path) == []


# --- a labeling session ----------------------------------------------------


def test_a_session_records_what_was_typed(tmp_path, monkeypatch) -> None:
    workspace = _workspace(tmp_path)
    first, second = labels.calibration_set()[:2]
    _seed_answer(workspace, first[0], first[1], "an answer")
    _seed_answer(workspace, second[0], second[1], "another answer")

    _type(monkeypatch, ["a", "y", "r", "n", "q"])
    labels.label_session(1, workspace)

    written = labels.read_labels(1, workspace)
    assert [(e.qid, e.behaviour, e.correct) for e in written] == [
        (first[0].qid, "answered", True),
        (second[0].qid, "refused", False),
    ]


def test_the_recorded_variant_is_the_one_the_set_assigned(tmp_path, monkeypatch) -> None:
    """Half the calibration items come from the weaker model. A session that
    recorded the wrong one would attribute an answer to a model that never
    produced it."""
    workspace = _workspace(tmp_path)
    first = labels.calibration_set()[0]
    _seed_answer(workspace, first[0], first[1], "an answer")

    _type(monkeypatch, ["a", "y", "q"])
    labels.label_session(1, workspace)

    assert labels.read_labels(1, workspace)[0].variant == first[1]


def test_quitting_immediately_records_nothing(tmp_path, monkeypatch) -> None:
    workspace = _workspace(tmp_path)
    first = labels.calibration_set()[0]
    _seed_answer(workspace, first[0], first[1], "an answer")

    _type(monkeypatch, ["q"])
    labels.label_session(1, workspace)

    assert labels.read_labels(1, workspace) == []


def test_a_session_resumes_where_it_stopped(tmp_path, monkeypatch) -> None:
    workspace = _workspace(tmp_path)
    first, second = labels.calibration_set()[:2]
    _seed_answer(workspace, first[0], first[1], "an answer")
    _seed_answer(workspace, second[0], second[1], "another answer")

    _type(monkeypatch, ["a", "y", "q"])
    labels.label_session(1, workspace)
    _type(monkeypatch, ["r", "y", "q"])
    labels.label_session(1, workspace)

    assert [e.qid for e in labels.read_labels(1, workspace)] == [first[0].qid, second[0].qid]


def test_an_invalid_key_is_rejected_rather_than_recorded(tmp_path, monkeypatch, capsys) -> None:
    workspace = _workspace(tmp_path)
    first = labels.calibration_set()[0]
    _seed_answer(workspace, first[0], first[1], "an answer")

    _type(monkeypatch, ["maybe", "a", "y", "q"])
    labels.label_session(1, workspace)

    assert "not one of" in capsys.readouterr().out
    assert [e.behaviour for e in labels.read_labels(1, workspace)] == ["answered"]


def test_an_item_with_no_cached_answer_is_skipped(tmp_path, monkeypatch, capsys) -> None:
    """Labeling a question whose answer was never generated would record a
    verdict about nothing."""
    workspace = _workspace(tmp_path)
    _type(monkeypatch, ["q"])
    labels.label_session(1, workspace)

    assert "no cached answer" in capsys.readouterr().out
    assert labels.read_labels(1, workspace) == []


def test_status_reports_both_rounds_and_the_spread(tmp_path, capsys) -> None:
    workspace = _workspace(tmp_path)
    labels.status(workspace)

    out = capsys.readouterr().out
    assert "42 answers" in out
    assert "round 1: 0/42" in out
    assert "claude-haiku-4-5" in out
