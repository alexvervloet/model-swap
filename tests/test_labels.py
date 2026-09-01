"""The calibration set has to be the same every round, on every machine."""

from __future__ import annotations

from pathlib import Path

from modelswap import judge, labels


def test_the_calibration_set_is_stable_across_calls() -> None:
    first = [(q.qid, v) for q, v in labels.calibration_set()]
    second = [(q.qid, v) for q, v in labels.calibration_set()]
    assert first == second


def test_the_calibration_set_is_stratified() -> None:
    """Not a random sample of the whole set: a judge that agrees on lookups
    while missing every refusal would average out to something that looks
    fine."""
    chosen = labels.calibration_set()
    counts: dict[str, int] = {}
    for question, _ in chosen:
        counts[question.stratum] = counts.get(question.stratum, 0) + 1

    assert len(counts) == 6
    assert all(count == labels.PER_STRATUM for count in counts.values())
    assert len(chosen) == 6 * labels.PER_STRATUM


def test_labels_append_and_read_back(tmp_path: Path) -> None:
    label = labels.Label(
        qid="q1",
        variant="claude-opus-5",
        sample=0,
        answer_digest=judge.digest("an answer"),
        correct=True,
        behaviour="answered",
        round=1,
        labeled_at="2026-09-01T00:00:00+00:00",
    )
    labels.append_label(label, tmp_path)
    labels.append_label(labels.Label(**{**label.__dict__, "qid": "q2", "correct": False}), tmp_path)

    read = labels.read_labels(1, tmp_path)
    assert [entry.qid for entry in read] == ["q1", "q2"]
    assert [entry.correct for entry in read] == [True, False]


def test_rounds_are_kept_apart(tmp_path: Path) -> None:
    """Round 2 must not be able to see round 1, and the simplest guarantee is
    that it never reads the same file."""
    base = {
        "qid": "q1",
        "variant": "claude-opus-5",
        "sample": 0,
        "answer_digest": "d",
        "behaviour": "answered",
        "labeled_at": "2026-09-01T00:00:00+00:00",
    }
    labels.append_label(labels.Label(**base, correct=True, round=1), tmp_path)  # type: ignore[arg-type]
    labels.append_label(labels.Label(**base, correct=False, round=2), tmp_path)  # type: ignore[arg-type]

    assert [entry.correct for entry in labels.read_labels(1, tmp_path)] == [True]
    assert [entry.correct for entry in labels.read_labels(2, tmp_path)] == [False]


def test_no_labels_reads_as_empty_rather_than_failing(tmp_path: Path) -> None:
    assert labels.read_labels(1, tmp_path) == []


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
