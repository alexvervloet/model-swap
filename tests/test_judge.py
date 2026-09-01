"""The judge's plumbing. What it decides is a question for the calibration
report; what it records has to be right regardless."""

from __future__ import annotations

from pathlib import Path

from modelswap import judge, questions
from tests.test_answers import _answer


def _question(expect: str = "answerable", notes: str = "£9.40.") -> questions.Question:
    return questions.Question(
        qid="q1",
        stratum="single",
        text="How much?",
        expect=expect,
        sources=("03-fares-and-tickets",) if expect == "answerable" else (),
        notes=notes,
    )


def test_a_citation_marker_is_detected() -> None:
    assert judge.has_citation('Yes [2] "because".')
    assert not judge.has_citation("Yes, because the policy says so.")
    assert not judge.has_citation("See section [a] of the handbook.")


def test_an_answered_refusal_question_does_not_match() -> None:
    verdict = judge.Verdict(reasoning="invented a policy", behaviour="answered", correct=False)
    judgment = judge.to_judgment(_question(expect="refusal"), _answer(), verdict)

    assert judgment.expected_behaviour == "refused"
    assert judgment.behaviour_matches is False


def test_a_refusal_is_never_marked_uncited() -> None:
    """A refusal has nothing to cite. Scoring it as uncited would make every
    correct refusal fail a metric it cannot pass."""
    verdict = judge.Verdict(reasoning="correctly declined", behaviour="refused", correct=True)
    judgment = judge.to_judgment(_question(expect="refusal"), _answer(text="No idea."), verdict)

    assert judgment.cited is True
    assert judgment.metrics == {"correct": True, "behaviour_matches": True, "cited": True}


def test_an_answer_without_a_citation_fails_only_that_metric() -> None:
    verdict = judge.Verdict(reasoning="right but bare", behaviour="answered", correct=True)
    judgment = judge.to_judgment(_question(), _answer(text="It is £9.40."), verdict)

    assert judgment.metrics == {"correct": True, "behaviour_matches": True, "cited": False}


def test_the_prompt_carries_the_reference_and_never_the_model() -> None:
    """Reference-based grading is the whole reason the notes exist. Naming the
    candidate would hand the judge something to prefer."""
    prompt = judge.build_prompt(_question(notes="£9.40, adult single."), "It is £9.40 [1].")

    assert "£9.40, adult single." in prompt
    assert "an answer" in prompt
    for variant in ("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"):
        assert variant not in prompt


def test_a_refusal_question_tells_the_judge_to_expect_one() -> None:
    prompt = judge.build_prompt(_question(expect="refusal", notes="Not written."), "No idea.")
    assert "a refusal" in prompt


def test_a_rejudged_answer_is_a_miss_when_the_answer_changed(tmp_path: Path) -> None:
    verdict = judge.Verdict(reasoning="fine", behaviour="answered", correct=True)
    judgment = judge.to_judgment(_question(), _answer(text="It is £9.40 [1]."), verdict)
    judge.write_cached(judgment, tmp_path)

    assert (
        judge.read_cached("q1", judgment.variant, 0, judgment.answer_digest, tmp_path) is not None
    )
    assert judge.read_cached("q1", judgment.variant, 0, judge.digest("different"), tmp_path) is None


def test_the_rubric_version_covers_the_judge_model() -> None:
    """Changing judge model changes what a score means as surely as changing
    the words, so both are in the key that invalidates the cache."""
    assert len(judge.RUBRIC_VERSION) == 64
    assert judge.digest(judge.RUBRIC) != judge.RUBRIC_VERSION
