"""Kappa is the part that has to be right: it is the number that decides
whether the judge grades anything at all."""

from __future__ import annotations

import pytest

from modelswap import agreement


def test_perfect_disagreement_is_negative() -> None:
    pairs = [(True, False), (False, True), (True, False), (False, True)]
    assert agreement.cohens_kappa(pairs) < 0


def test_perfect_agreement_on_a_balanced_set_is_one() -> None:
    pairs = [(True, True), (False, False), (True, True), (False, False)]
    assert agreement.cohens_kappa(pairs) == pytest.approx(1.0)


def test_a_rater_that_always_says_correct_scores_zero_kappa() -> None:
    """The whole reason kappa is reported next to the raw rate. Nine correct
    answers in ten, a judge that never says otherwise, and 90% agreement that
    means nothing."""
    pairs = [(True, True)] * 9 + [(False, True)]
    scored = agreement.agreement_of(pairs)

    assert scored.rate == pytest.approx(0.9)
    assert scored.kappa == pytest.approx(0.0)
    assert not scored.clears_floor


def test_unanimous_agreement_reports_zero_rather_than_dividing_by_zero() -> None:
    """Both raters said correct every time. Chance agreement is 1.0 and kappa
    is undefined; the rate beside it is what says what happened."""
    pairs = [(True, True)] * 20
    scored = agreement.agreement_of(pairs)

    assert scored.rate == 1.0
    assert scored.kappa == 0.0
    assert not scored.clears_floor


def test_the_floor_needs_both_numbers() -> None:
    high_rate_low_kappa = agreement.Agreement(n=100, agreed=95, kappa=0.1)
    low_rate_high_kappa = agreement.Agreement(n=100, agreed=70, kappa=0.9)
    both = agreement.Agreement(n=100, agreed=90, kappa=0.7)

    assert not high_rate_low_kappa.clears_floor
    assert not low_rate_high_kappa.clears_floor
    assert both.clears_floor


def test_an_empty_comparison_does_not_clear_the_floor() -> None:
    """No labels must never read as a pass."""
    assert not agreement.agreement_of([]).clears_floor


def test_the_floor_is_declared_in_the_repository() -> None:
    """Predeclared, before any label existed. The git history is the proof;
    this test is the reminder not to move it after seeing a result."""
    assert agreement.MIN_AGREEMENT == 0.85
    assert agreement.MIN_KAPPA == 0.60


# --- the report ------------------------------------------------------------


def _workspace(tmp_path):
    from modelswap.sut import repo_root

    (tmp_path / "corpus").symlink_to(repo_root() / "corpus")
    (tmp_path / "questions").symlink_to(repo_root() / "questions")
    return tmp_path


def _seed(root, *, human: list[bool], model: list[bool], rounds=(1,)):
    """Label and judge the first N calibration items with the given verdicts."""
    from modelswap import answers, corpus, judge, labels

    items = labels.calibration_set()[: len(human)]
    for (question, variant), human_says, model_says in zip(items, human, model, strict=True):
        text = f"answer to {question.qid}"
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
        for round_number in rounds:
            labels.append_label(
                labels.Label(
                    qid=question.qid,
                    variant=variant,
                    sample=0,
                    answer_digest=judge.digest(text),
                    correct=human_says,
                    behaviour="answered",
                    round=round_number,
                    labeled_at="2026-09-01T00:00:00+00:00",
                ),
                root,
            )
        judge.write_cached(
            judge.Judgment(
                qid=question.qid,
                variant=variant,
                sample=0,
                correct=model_says,
                behaviour="answered",
                expected_behaviour="answered",
                behaviour_matches=True,
                cited=True,
                reasoning="because",
                rubric_version=judge.RUBRIC_VERSION,
                answer_digest=judge.digest(text),
            ),
            root,
        )
    return items


def test_the_report_refuses_with_no_labels(tmp_path, capsys) -> None:
    assert agreement.report(_workspace(tmp_path)) == 1
    assert "No labels yet" in capsys.readouterr().out


def test_one_round_is_reported_as_provisional(tmp_path, capsys) -> None:
    """The rubric was written while looking at round 1, so agreement against it
    is marking your own homework and the report has to say so."""
    root = _workspace(tmp_path)
    _seed(root, human=[True] * 6 + [False] * 4, model=[True] * 6 + [False] * 4)

    exit_code = agreement.report(root)
    out = capsys.readouterr().out

    assert "round 2 not labeled" in out
    assert "provisional" in out
    assert exit_code == 1, "one round can never certify the judge"


def test_a_judge_that_agrees_clears_the_floor(tmp_path, capsys) -> None:
    root = _workspace(tmp_path)
    verdicts = [True] * 6 + [False] * 4
    _seed(root, human=verdicts, model=verdicts, rounds=(1, 2))

    exit_code = agreement.report(root)
    out = capsys.readouterr().out

    assert "CLEARS the floor" in out
    assert "self-agreement (the ceiling)" in out
    assert exit_code == 0


def test_a_judge_that_disagrees_is_refused_and_the_cases_are_named(tmp_path, capsys) -> None:
    root = _workspace(tmp_path)
    human = [True] * 5 + [False] * 5
    model = [True] * 10  # says correct to everything
    items = _seed(root, human=human, model=model, rounds=(1, 2))

    exit_code = agreement.report(root)
    out = capsys.readouterr().out

    assert "BELOW the floor" in out
    assert "5 disagreement(s)" in out
    assert items[9][0].qid in out or items[5][0].qid in out
    assert exit_code == 1


def test_disagreements_are_broken_down_by_stratum(tmp_path, capsys) -> None:
    """Where the judge fails matters more than how often. A judge that is fine
    on lookups and blind on refusals is not 90% good."""
    root = _workspace(tmp_path)
    _seed(root, human=[False] * 10, model=[True] * 10, rounds=(1, 2))

    agreement.report(root)
    out = capsys.readouterr().out

    assert "by stratum:" in out
    assert any(word in out for word in ("single", "multihop", "override"))
