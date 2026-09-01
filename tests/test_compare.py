"""The comparison report reads the cache and spends nothing. Every number in it
was paid for once."""

from __future__ import annotations

from pathlib import Path

from modelswap import answers, compare, judge
from modelswap.sut import repo_root


def _workspace(tmp_path: Path) -> Path:
    (tmp_path / "corpus").symlink_to(repo_root() / "corpus")
    (tmp_path / "questions").symlink_to(repo_root() / "questions")
    return tmp_path


def _answer(root: Path, qid: str, variant: str, cost: float, seconds: float) -> answers.Answer:
    record = answers.Answer(
        qid=qid,
        variant=variant,
        sample=0,
        question="q",
        text=f"answer to {qid}",
        sources=[],
        input_tokens=3000,
        output_tokens=200,
        cost_usd=cost,
        seconds=seconds,
        corpus_version="abc123def456",
    )
    answers.write_cached(record, root)
    return record


def test_a_failed_answer_is_left_out_of_the_averages(tmp_path: Path) -> None:
    """An outage that cost nothing and produced nothing would otherwise drag
    the cost per hundred down and look like an improvement."""
    _answer(tmp_path, "q1", "claude-haiku-4-5", 0.01, 2.0)
    answers.write_cached(
        answers.Answer(
            qid="q2",
            variant="claude-haiku-4-5",
            sample=0,
            question="q",
            text="",
            sources=[],
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            seconds=0.0,
            corpus_version="abc123def456",
            error="failed",
        ),
        tmp_path,
    )

    rows = compare.collect(tmp_path)
    assert len(rows) == 1
    assert rows[0].n == 1


def test_ungraded_variants_still_report_cost_and_latency(tmp_path: Path) -> None:
    """Cost and latency are facts about the run. They do not need a rubric."""
    _answer(tmp_path, "q1", "claude-haiku-4-5", 0.01, 2.0)

    row = compare.collect(tmp_path)[0]
    assert row.graded == 0
    assert row.accuracy is None
    assert row.cost_per_hundred == 1.0


def test_reference_variants_are_marked_as_such(tmp_path: Path, capsys) -> None:
    """Opus is not a candidate any more. Its answers are still real and still
    paid for, and the report has to show them without implying they are part of
    the comparison."""
    _answer(tmp_path, "q1", "claude-opus-5", 0.02, 5.0)
    _answer(tmp_path, "q1", "claude-haiku-4-5", 0.002, 2.0)

    compare.report(_workspace(tmp_path))
    out = capsys.readouterr().out

    assert "claude-opus-5 (reference)" in out
    assert "claude-haiku-4-5 (reference)" not in out
    assert "10.0x" in out


def test_accuracy_appears_once_the_answers_are_graded(tmp_path: Path) -> None:
    record = _answer(tmp_path, "q1", "claude-haiku-4-5", 0.01, 2.0)
    judge.write_cached(
        judge.Judgment(
            qid="q1",
            variant="claude-haiku-4-5",
            sample=0,
            correct=True,
            behaviour="answered",
            expected_behaviour="answered",
            behaviour_matches=True,
            cited=True,
            reasoning="because",
            rubric_version=judge.RUBRIC_VERSION,
            answer_digest=judge.digest(record.text),
            judge_model=judge.JUDGE_MODEL,
        ),
        tmp_path,
    )

    row = compare.collect(tmp_path)[0]
    assert (row.graded, row.correct) == (1, 1)
    assert row.accuracy == 1.0


def test_a_stale_verdict_does_not_count(tmp_path: Path) -> None:
    """The verdict on disk graded a different answer text. Counting it would
    attribute an old grade to a new answer."""
    _answer(tmp_path, "q1", "claude-haiku-4-5", 0.01, 2.0)
    judge.write_cached(
        judge.Judgment(
            qid="q1",
            variant="claude-haiku-4-5",
            sample=0,
            correct=True,
            behaviour="answered",
            expected_behaviour="answered",
            behaviour_matches=True,
            cited=True,
            reasoning="because",
            rubric_version=judge.RUBRIC_VERSION,
            answer_digest=judge.digest("some other answer"),
            judge_model=judge.JUDGE_MODEL,
        ),
        tmp_path,
    )

    assert compare.collect(tmp_path)[0].graded == 0


def test_an_empty_cache_says_so(tmp_path: Path, capsys) -> None:
    assert compare.report(tmp_path) == 1
    assert "no cached answers" in capsys.readouterr().out
