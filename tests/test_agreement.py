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
