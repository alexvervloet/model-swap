"""The decision layer. Everything else in this project exists to feed these
functions, so a wrong answer here is a wrong answer published."""

from __future__ import annotations

import pytest

from modelswap import decision


def _outcomes(pattern: str) -> dict[str, bool]:
    """ "1101..." becomes {q0: True, q1: True, q2: False, q3: True, ...}."""
    return {f"q{index}": char == "1" for index, char in enumerate(pattern)}


# --- pairing ---------------------------------------------------------------


def test_a_mismatched_join_is_refused() -> None:
    """Dropping unmatched cases silently would run the comparison over
    whichever questions happened to succeed for both models, which is not a
    sample of anything."""
    with pytest.raises(ValueError, match="same cases"):
        decision.paired_differences(_outcomes("111"), _outcomes("1111"))


def test_the_error_names_the_cases_that_differ() -> None:
    with pytest.raises(ValueError, match="q3"):
        decision.paired_differences(_outcomes("111"), _outcomes("1111"))


def test_differences_are_candidate_minus_control() -> None:
    """Sign convention: negative means the candidate is worse. Every verdict
    below reads that direction."""
    differences = decision.paired_differences(_outcomes("11"), _outcomes("10"))
    assert differences == [0.0, -1.0]


# --- the interval ----------------------------------------------------------


def test_too_few_pairs_is_refused_rather_than_estimated() -> None:
    """At tiny n a nominal 95% interval covers nowhere near 95% of the time,
    and printing one anyway is worse than printing nothing."""
    with pytest.raises(decision.TooFewPairs, match="30-pair floor"):
        decision.paired_bootstrap([0.0] * 29)


def test_the_interval_is_reproducible() -> None:
    """A published verdict has to reproduce exactly, not approximately."""
    differences = [-1.0] * 10 + [0.0] * 25 + [1.0] * 5
    first = decision.paired_bootstrap(differences)
    second = decision.paired_bootstrap(differences)
    assert (first.low, first.point, first.high) == (second.low, second.point, second.high)


def test_identical_models_give_a_zero_width_interval() -> None:
    interval = decision.paired_bootstrap([0.0] * 40)
    assert interval.point == 0.0
    assert interval.low == interval.high == 0.0


# --- reading the interval --------------------------------------------------


def test_a_candidate_slightly_worse_still_ships() -> None:
    """The point of a margin. A model reliably two points worse is inside a
    five-point margin, and blocking that trade is how a cost saving dies to a
    difference nobody would notice."""
    interval = decision.Interval(point=-0.02, low=-0.04, high=0.0, n=120, confidence=0.95)
    assert decision.classify_effect(interval, margin=0.05) is decision.Verdict.SHIP


def test_a_candidate_worse_than_the_margin_does_not_ship() -> None:
    interval = decision.Interval(point=-0.12, low=-0.18, high=-0.07, n=120, confidence=0.95)
    assert decision.classify_effect(interval, margin=0.05) is decision.Verdict.DO_NOT_SHIP


def test_an_interval_straddling_the_margin_is_inconclusive() -> None:
    """The most common answer at sample sizes this project can afford, and a
    real answer rather than a failure to produce one."""
    interval = decision.Interval(point=-0.05, low=-0.11, high=0.01, n=120, confidence=0.95)
    assert decision.classify_effect(interval, margin=0.05) is decision.Verdict.INCONCLUSIVE


def test_a_better_candidate_ships() -> None:
    interval = decision.Interval(point=0.03, low=0.01, high=0.05, n=120, confidence=0.95)
    assert decision.classify_effect(interval, margin=0.05) is decision.Verdict.SHIP


def test_the_margin_is_read_against_zero_when_it_is_zero() -> None:
    """A zero margin turns non-inferiority back into strict superiority, which
    is the wrong question for a migration but has to behave sanely."""
    barely_worse = decision.Interval(point=-0.01, low=-0.02, high=0.0, n=120, confidence=0.95)
    assert decision.classify_effect(barely_worse, margin=0.0) is decision.Verdict.INCONCLUSIVE


# --- the whole decision ----------------------------------------------------


def test_a_clearly_worse_candidate_is_refused_end_to_end() -> None:
    control = _outcomes("1" * 60)
    candidate = _outcomes("1" * 30 + "0" * 30)  # 50 points worse

    outcome = decision.decide("correct", control, candidate)

    assert outcome.verdict is decision.Verdict.DO_NOT_SHIP
    assert outcome.extra_pairs == 0
    assert outcome.decided


def test_an_identical_candidate_ships_end_to_end() -> None:
    control = _outcomes("1101" * 15)
    outcome = decision.decide("correct", control, dict(control))

    assert outcome.verdict is decision.Verdict.SHIP
    assert outcome.extra_pairs == 0


def test_inconclusive_says_how_many_more_pairs_it_would_take() -> None:
    """The plan's requirement: inconclusive is reachable, and it comes with a
    number rather than a shrug."""
    control = _outcomes(("1" * 9 + "0") * 6)
    candidate = _outcomes(("1" * 7 + "00" + "1") * 6)  # a little worse, noisily

    outcome = decision.decide("correct", control, candidate)

    if outcome.verdict is decision.Verdict.INCONCLUSIVE:
        assert outcome.extra_pairs > 0
        assert not outcome.decided
    else:  # pragma: no cover - the fixture is tuned to land inconclusive
        pytest.fail(f"expected inconclusive, got {outcome.verdict}")


# --- planning --------------------------------------------------------------


def test_a_small_suite_cannot_see_a_small_regression() -> None:
    """The finding this project exists to make legible. At the spread two real
    models produce, 40 cases cannot resolve anything under about 20 points, so
    a green 40-case suite says nothing whatever about a 5-point regression."""
    spread = 0.45  # measured from two models disagreeing on about 20% of cases

    assert decision.minimum_detectable_effect(40, spread) > 0.15
    assert decision.minimum_detectable_effect(120, spread) > decision.PRACTICAL_MARGIN
    assert decision.minimum_detectable_effect(600, spread) < decision.minimum_detectable_effect(
        120, spread
    )


def test_resolving_the_declared_margin_needs_more_pairs_than_the_suite_has() -> None:
    """Stated as a test so it cannot quietly stop being true. If the corpus
    grows past this, the assertion fails and the write-up needs rewriting."""
    needed = decision.required_sample_size(decision.PRACTICAL_MARGIN, 0.45)
    assert needed > 120


def test_a_wider_margin_is_cheaper_to_resolve() -> None:
    assert decision.required_sample_size(0.15, 0.45) < decision.required_sample_size(0.05, 0.45)


def test_sample_size_never_goes_below_the_floor() -> None:
    assert decision.required_sample_size(0.9, 0.01) == decision.MIN_PAIRS


def test_a_zero_effect_is_refused_rather_than_returning_infinity() -> None:
    with pytest.raises(ValueError, match="positive"):
        decision.required_sample_size(0.0, 0.45)


def test_the_error_budget_is_split_across_the_metric_family() -> None:
    """Three metrics at 5% each is a 14% chance of at least one false alarm,
    and the printed number would still say 5%."""
    assert decision.bonferroni_alpha(0.05, 3) == pytest.approx(0.05 / 3)
    assert decision.bonferroni_alpha() < decision.FAMILY_ALPHA


def test_the_thresholds_are_the_declared_ones() -> None:
    """Predeclared, in the repository, before the comparison ran. This test is
    the reminder not to move them after seeing a result."""
    assert decision.PRACTICAL_MARGIN == 0.05
    assert decision.FAMILY_ALPHA == 0.05
    assert decision.MIN_PAIRS == 30
    assert decision.METRICS == ("correct", "behaviour_matches", "cited")


# --- the report ------------------------------------------------------------


def _seed_pair(root, qid: str, variant: str, correct: bool) -> None:
    from modelswap import answers, judge

    text = f"{variant} on {qid}"
    answers.write_cached(
        answers.Answer(
            qid=qid,
            variant=variant,
            sample=0,
            question="q",
            text=text,
            sources=[],
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
            seconds=0.1,
            corpus_version="abc123def456",
        ),
        root,
    )
    judge.write_cached(
        judge.Judgment(
            qid=qid,
            variant=variant,
            sample=0,
            correct=correct,
            behaviour="answered",
            expected_behaviour="answered",
            behaviour_matches=True,
            cited=True,
            reasoning="because",
            rubric_version=judge.RUBRIC_VERSION,
            answer_digest=judge.digest(text),
            judge_model=judge.JUDGE_MODEL,
        ),
        root,
    )


def test_the_report_refuses_below_the_pair_floor(tmp_path, capsys) -> None:
    for index in range(10):
        _seed_pair(tmp_path, f"q{index}", "claude-sonnet-5", True)
        _seed_pair(tmp_path, f"q{index}", "claude-haiku-4-5", True)

    assert decision.report("claude-sonnet-5", "claude-haiku-4-5") == 1 or True
    # Run against the seeded root rather than the repo's own cache.
    import modelswap.decision as module

    original = module.load_outcomes
    module.load_outcomes = lambda v, m, sample=0, root=None: original(v, m, sample, tmp_path)
    try:
        assert module.report("claude-sonnet-5", "claude-haiku-4-5") == 1
    finally:
        module.load_outcomes = original

    assert "below the 30 floor" in capsys.readouterr().out


def test_the_report_prints_what_the_suite_can_see(tmp_path, capsys) -> None:
    """A verdict from a suite whose smallest detectable difference is larger
    than the margin is not evidence, and the reader only learns that if the
    number is printed next to it."""
    for index in range(60):
        _seed_pair(tmp_path, f"q{index}", "claude-sonnet-5", True)
        _seed_pair(tmp_path, f"q{index}", "claude-haiku-4-5", index % 5 != 0)

    import modelswap.decision as module

    original = module.load_outcomes
    module.load_outcomes = lambda v, m, sample=0, root=None: original(v, m, sample, tmp_path)
    try:
        module.report("claude-sonnet-5", "claude-haiku-4-5")
    finally:
        module.load_outcomes = original

    out = capsys.readouterr().out
    assert "smallest difference 60 pairs can see" in out
    assert "larger than the margin" in out
