"""Turn paired per-case outcomes into a release decision.

    python -m modelswap.decision --control claude-sonnet-5 --candidate claude-haiku-4-5

Free to run. It reads cached verdicts and computes; it never calls a model.

**The question is non-inferiority, not superiority.** Nobody migrates to a
cheaper model hoping it is better. The question is whether it is worse by more
than you are willing to accept, and that shape of question has a different
answer to "is there a difference". A candidate can be genuinely, measurably
worse and still be the right thing to ship at an eighth of the price. So the
verdict is read against a margin declared in advance, not against zero.

**Pairing is what makes 120 cases enough.** Both models answer the same
question, so the per-case difficulty cancels: a question they both get right
and a question they both get wrong contribute nothing to the interval either
way. Comparing two independent rates over the same corpus throws that away and
needs several times the sample for the same resolution.

**The thresholds below are declared here, in the repository, before the
comparison has run.** That ordering is the only thing that makes them mean
anything, and the git history is the proof. Change them if they are wrong for
your product, but change them before you see a result, not after.

The statistics follow the shapes taught in `evals-deep-dive/evals/decision.py`
and keep its names, so the lineage is legible. Percentile bootstrap, normal
planning approximations, Bonferroni across the metric family: readable and
conservative rather than universal. Clustered users, adaptive traffic and rare
outcomes all need a design validated for their own sampling process.
"""

from __future__ import annotations

import argparse
import math
import random
import statistics
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

# How much worse the candidate may be, in proportion of cases, and still ship.
# Five points of accuracy for an eighth of the bill is a trade a real operator
# would take; five points on a legal or medical corpus would not be. This is a
# product decision wearing a statistical costume, which is why it is a constant
# with a comment rather than a default buried in a signature.
PRACTICAL_MARGIN = 0.05

# One error budget, spent across every metric the decision looks at. Testing
# three metrics at 5% each is a 14% chance of at least one false alarm, and the
# printed number would still say 5%.
FAMILY_ALPHA = 0.05
METRICS = ("correct", "behaviour_matches", "cited")

# Planning target. The power to detect the margin if the candidate really is at
# the margin.
POWER = 0.80

# Below this, a percentile interval's real coverage is nowhere near its nominal
# coverage, and a sequential look is worse than no look. The dive's own module
# refuses schedules starting below 30 for the same reason.
MIN_PAIRS = 30

BOOTSTRAP_ITERATIONS = 10_000
BOOTSTRAP_SEED = 20260901


class Verdict(str, Enum):
    SHIP = "ship"
    DO_NOT_SHIP = "do not ship"
    INCONCLUSIVE = "inconclusive"


class TooFewPairs(ValueError):
    """Not enough paired cases for an interval worth reading."""


@dataclass(frozen=True)
class Interval:
    """A percentile interval for the mean candidate-minus-control difference."""

    point: float
    low: float
    high: float
    n: int
    confidence: float

    def __str__(self) -> str:
        return f"{self.point:+.1%} [{self.low:+.1%}, {self.high:+.1%}]"


@dataclass(frozen=True)
class Decision:
    metric: str
    interval: Interval
    margin: float
    verdict: Verdict
    extra_pairs: int
    """How many more paired cases would resolve an inconclusive result. Zero
    when the verdict is decided."""

    @property
    def decided(self) -> bool:
        return self.verdict is not Verdict.INCONCLUSIVE


def paired_differences(control: Mapping[str, bool], candidate: Mapping[str, bool]) -> list[float]:
    """Candidate minus control, per case, over the cases both answered.

    Refuses a join that is not the same set of cases on both sides. Silently
    dropping unmatched cases is how a comparison ends up run over whichever
    questions happened to succeed for both models, which is not a sample of
    anything.
    """
    if set(control) != set(candidate):
        only_control = sorted(set(control) - set(candidate))
        only_candidate = sorted(set(candidate) - set(control))
        raise ValueError(
            "control and candidate must cover the same cases; "
            f"control only: {only_control[:5]}, candidate only: {only_candidate[:5]}"
        )
    return [float(candidate[case]) - float(control[case]) for case in sorted(control)]


def paired_bootstrap(
    differences: Sequence[float],
    alpha: float = FAMILY_ALPHA,
    iterations: int = BOOTSTRAP_ITERATIONS,
    seed: int = BOOTSTRAP_SEED,
) -> Interval:
    """Resample whole case pairs to get an interval on the mean difference.

    Whole pairs, not individual outcomes: the pairing is the thing carrying the
    precision, and resampling the two sides independently would discard it.

    Seeded, so a published verdict reproduces exactly rather than approximately.
    """
    n = len(differences)
    if n < MIN_PAIRS:
        raise TooFewPairs(
            f"{n} pairs is below the {MIN_PAIRS}-pair floor. A percentile interval"
            " over fewer covers far less often than it claims to."
        )

    # S311: a seeded resampler, not a security primitive. Determinism is the
    # requirement.
    rng = random.Random(seed)  # noqa: S311
    means = sorted(statistics.fmean(rng.choices(differences, k=n)) for _ in range(iterations))
    lower = means[int(iterations * (alpha / 2))]
    upper = means[min(int(iterations * (1 - alpha / 2)), iterations - 1)]
    return Interval(
        point=statistics.fmean(differences),
        low=lower,
        high=upper,
        n=n,
        confidence=1 - alpha,
    )


def classify_effect(interval: Interval, margin: float = PRACTICAL_MARGIN) -> Verdict:
    """Read the interval against a margin, not against zero.

    Ship when the whole interval is better than "worse by the margin", which
    includes intervals sitting entirely below zero: a candidate reliably two
    points worse is still inside a five-point margin, and pretending otherwise
    is how a cost saving gets blocked by a difference nobody would notice.

    Do not ship when the whole interval is worse than the margin. Everything
    else is inconclusive, which is a real answer and the most common one at
    sample sizes this project can afford.
    """
    if interval.low >= -margin:
        return Verdict.SHIP
    if interval.high < -margin:
        return Verdict.DO_NOT_SHIP
    return Verdict.INCONCLUSIVE


def _z(probability: float) -> float:
    quantile: float = statistics.NormalDist().inv_cdf(probability)
    return quantile


def required_sample_size(
    effect: float, sd: float, alpha: float = FAMILY_ALPHA, power: float = POWER
) -> int:
    """Paired cases needed to detect `effect` at this alpha and power.

    A normal approximation, which is the planning tool rather than the decision
    tool. Use it to find out whether a question is answerable at all before
    paying to answer it.
    """
    if effect <= 0:
        raise ValueError("effect must be positive")
    if sd <= 0:
        return MIN_PAIRS
    z_alpha = _z(1 - alpha / 2)
    z_beta = _z(power)
    pairs = ((z_alpha + z_beta) * sd / effect) ** 2
    return max(MIN_PAIRS, math.ceil(pairs))


def minimum_detectable_effect(
    n: int, sd: float, alpha: float = FAMILY_ALPHA, power: float = POWER
) -> float:
    """The smallest true difference this many pairs could reliably detect.

    The number most eval suites cannot survive being asked. A 40-case suite at
    a typical spread cannot see a five-point regression, so a green run on one
    says nothing about a five-point regression, and the run will still print a
    reassuring percentage.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    return (_z(1 - alpha / 2) + _z(power)) * sd / math.sqrt(n)


def bonferroni_alpha(family_alpha: float = FAMILY_ALPHA, decisions: int = len(METRICS)) -> float:
    """Split one error budget across the decisions being made from it."""
    if decisions < 1:
        raise ValueError("decisions must be at least 1")
    return family_alpha / decisions


def decide(
    metric: str,
    control: Mapping[str, bool],
    candidate: Mapping[str, bool],
    margin: float = PRACTICAL_MARGIN,
    alpha: float | None = None,
) -> Decision:
    """One metric, one verdict, and the cost of resolving it if undecided."""
    differences = paired_differences(control, candidate)
    interval = paired_bootstrap(differences, alpha=alpha or bonferroni_alpha())
    verdict = classify_effect(interval, margin)

    extra = 0
    if verdict is Verdict.INCONCLUSIVE:
        spread = statistics.stdev(differences) if len(differences) > 1 else 0.0
        # The gap still to be resolved: how far the interval reaches past the
        # margin. Sizing for the margin itself would answer a question nobody
        # asked and cost several times more.
        gap = abs(interval.low + margin)
        needed = required_sample_size(max(gap, 1e-6), spread, alpha or bonferroni_alpha())
        extra = max(0, needed - interval.n)

    return Decision(
        metric=metric,
        interval=interval,
        margin=margin,
        verdict=verdict,
        extra_pairs=extra,
    )


def load_outcomes(
    variant: str, metric: str, sample: int = 0, root: object = None
) -> dict[str, bool]:
    """One metric's per-case outcomes for a variant, from cached verdicts."""
    from pathlib import Path  # noqa: PLC0415

    from modelswap import answers, judge  # noqa: PLC0415

    typed_root = root if isinstance(root, Path) else None
    outcomes: dict[str, bool] = {}
    for answer in answers.iter_cached(typed_root):
        if answer.variant != variant or answer.sample != sample:
            continue
        verdict = judge.read_cached(
            answer.qid, variant, sample, judge.digest(answer.text), typed_root
        )
        if verdict is not None:
            outcomes[answer.qid] = verdict.metrics[metric]
    return outcomes


def report(control: str, candidate: str, margin: float = PRACTICAL_MARGIN) -> int:
    print(f"{candidate} against {control}")
    print(f"  margin: {margin:.0%} worse is acceptable")
    print(
        f"  alpha:  {bonferroni_alpha():.4f} per metric ({FAMILY_ALPHA:.0%} across {len(METRICS)})\n"
    )

    decided = 0
    for metric in METRICS:
        control_outcomes = load_outcomes(control, metric)
        candidate_outcomes = load_outcomes(candidate, metric)
        shared = set(control_outcomes) & set(candidate_outcomes)
        if len(shared) < MIN_PAIRS:
            print(f"  {metric:20} {len(shared)} paired case(s): below the {MIN_PAIRS} floor")
            continue

        outcome = decide(
            metric,
            {q: control_outcomes[q] for q in shared},
            {q: candidate_outcomes[q] for q in shared},
            margin,
        )
        line = f"  {metric:20} {outcome.interval}  {outcome.verdict.value}"
        if outcome.extra_pairs:
            line += f", needs ~{outcome.extra_pairs} more pairs"
        print(line)
        decided += int(outcome.decided)

        # What the suite could see even in principle, printed next to what it
        # did see. A verdict of "ship" from a suite whose smallest detectable
        # difference is larger than the margin is not evidence of anything, and
        # the only way a reader learns that is if the number is right there.
        differences = paired_differences(
            {q: control_outcomes[q] for q in shared},
            {q: candidate_outcomes[q] for q in shared},
        )
        spread = statistics.stdev(differences) if len(differences) > 1 else 0.0
        if spread:
            mde = minimum_detectable_effect(len(shared), spread, bonferroni_alpha())
            note = "" if mde <= margin else "  <-- larger than the margin"
            print(f"  {'':20} smallest difference {len(shared)} pairs can see: {mde:.1%}{note}")
            if mde > margin:
                needed = required_sample_size(margin, spread, bonferroni_alpha())
                print(f"  {'':20} resolving the margin itself needs ~{needed} pairs")

    if not decided:
        print("\nnothing decided. Generate and judge both variants first.")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="A release verdict from cached verdicts")
    parser.add_argument("--control", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument(
        "--margin",
        type=float,
        default=PRACTICAL_MARGIN,
        help=f"how much worse the candidate may be and still ship (default {PRACTICAL_MARGIN})",
    )
    args = parser.parse_args()
    return report(args.control, args.candidate, args.margin)


if __name__ == "__main__":
    sys.exit(main())
