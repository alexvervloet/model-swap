"""Two judges over one set of answers. The archived verdicts are real and
already paid for; what they are worth depends entirely on this comparison being
right."""

from __future__ import annotations

from pathlib import Path

from modelswap import answers, judge, judges

ARCHIVED = "aaaaaaaaaaaa"


def _answer(root: Path, qid: str, variant: str, text: str) -> answers.Answer:
    record = answers.Answer(
        qid=qid,
        variant=variant,
        sample=0,
        question=f"q for {qid}",
        text=text,
        sources=[],
        input_tokens=1,
        output_tokens=1,
        cost_usd=0.0,
        seconds=0.1,
        corpus_version="abc123def456",
    )
    answers.write_cached(record, root)
    return record


def _verdict(root: Path, record: answers.Answer, correct: bool, rubric: str | None) -> None:
    judgment = judge.Judgment(
        qid=record.qid,
        variant=record.variant,
        sample=0,
        correct=correct,
        behaviour="answered",
        expected_behaviour="answered",
        behaviour_matches=True,
        cited=True,
        reasoning="because",
        answer_digest=judge.digest(record.text),
        rubric_version=rubric or judge.RUBRIC_VERSION,
        judge_model="claude-opus-5" if rubric else judge.JUDGE_MODEL,
    )
    path = judge._path(root, record.variant, 0, record.qid, rubric)
    path.parent.mkdir(parents=True, exist_ok=True)
    import json
    from dataclasses import asdict

    path.write_text(json.dumps(asdict(judgment), indent=2, sort_keys=True), encoding="utf-8")


def test_only_answers_graded_by_both_are_paired(tmp_path: Path) -> None:
    """An answer one judge never saw contributes nothing and must not be
    counted as agreement."""
    both = _answer(tmp_path, "q1", "claude-haiku-4-5", "one")
    archived_only = _answer(tmp_path, "q2", "claude-haiku-4-5", "two")
    current_only = _answer(tmp_path, "q3", "claude-haiku-4-5", "three")

    _verdict(tmp_path, both, True, ARCHIVED)
    _verdict(tmp_path, both, True, None)
    _verdict(tmp_path, archived_only, True, ARCHIVED)
    _verdict(tmp_path, current_only, True, None)

    pairings = judges.pair_up(ARCHIVED, tmp_path)
    assert len(pairings) == 1
    assert pairings[0].scored.n == 1


def test_disagreement_lowers_the_rate(tmp_path: Path) -> None:
    for index in range(10):
        record = _answer(tmp_path, f"q{index}", "claude-haiku-4-5", f"answer {index}")
        _verdict(tmp_path, record, True, ARCHIVED)
        _verdict(tmp_path, record, index < 7, None)

    pairing = judges.pair_up(ARCHIVED, tmp_path)[0]
    assert pairing.scored.n == 10
    assert pairing.scored.rate == 0.7


def test_the_generosity_gap_is_signed_towards_the_retired_judge(tmp_path: Path) -> None:
    """Positive means the retired judge said correct more often. That sign is
    the whole reading of the number, so it gets its own test."""
    for index in range(10):
        record = _answer(tmp_path, f"q{index}", "claude-opus-5", f"answer {index}")
        _verdict(tmp_path, record, True, ARCHIVED)  # retired: all correct
        _verdict(tmp_path, record, index < 6, None)  # current: 6 of 10

    pairing = judges.pair_up(ARCHIVED, tmp_path)[0]
    assert pairing.archived_rate == 1.0
    assert pairing.current_rate == 0.6
    assert pairing.generosity_gap == 0.4


def test_self_preference_shows_as_a_spread_between_variants(tmp_path: Path, capsys) -> None:
    """The measurement that matters: a retired judge generous to its own
    family's answers and not to the other's."""
    for index in range(10):
        own = _answer(tmp_path, f"o{index}", "claude-opus-5", f"opus {index}")
        _verdict(tmp_path, own, True, ARCHIVED)
        _verdict(tmp_path, own, index < 5, None)

        other = _answer(tmp_path, f"h{index}", "claude-haiku-4-5", f"haiku {index}")
        _verdict(tmp_path, other, index < 8, ARCHIVED)
        _verdict(tmp_path, other, index < 8, None)

    judges.report(tmp_path)
    out = capsys.readouterr().out

    assert "claude-opus-5" in out
    assert "+50%" in out  # generous to its own family
    assert "+0%" in out  # even-handed on the other
    assert "spread: 50%" in out


def test_the_archived_judge_model_is_read_from_the_records(tmp_path: Path) -> None:
    record = _answer(tmp_path, "q1", "claude-haiku-4-5", "one")
    _verdict(tmp_path, record, True, ARCHIVED)

    assert judges.archived_judge_model(ARCHIVED, tmp_path) == "claude-opus-5"


def test_verdicts_written_before_the_field_existed_say_so(tmp_path: Path) -> None:
    """170 real verdicts predate `judge_model`. They still load, and the report
    says the model is unrecorded rather than guessing."""
    record = _answer(tmp_path, "q1", "claude-haiku-4-5", "one")
    _verdict(tmp_path, record, True, ARCHIVED)
    path = judge._path(tmp_path, "claude-haiku-4-5", 0, "q1", ARCHIVED)
    import json

    stored = json.loads(path.read_text())
    del stored["judge_model"]
    path.write_text(json.dumps(stored), encoding="utf-8")

    assert judge.read_cached("q1", "claude-haiku-4-5", 0, judge.digest("one"), tmp_path, ARCHIVED)
    assert judges.archived_judge_model(ARCHIVED, tmp_path) == "unrecorded"


def test_nothing_to_compare_is_reported_rather_than_crashing(tmp_path: Path, capsys) -> None:
    assert judges.report(tmp_path) == 1
    assert "no retired rubrics" in capsys.readouterr().out
