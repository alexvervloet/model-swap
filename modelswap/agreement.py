"""Is the judge worth listening to?

    python -m modelswap.agreement

Nothing in this project reports a quality score until this does. A judge is a
measuring instrument, and an instrument nobody checked against a known quantity
is a number generator.

Three figures, and the order matters.

**Self-agreement** is how often the same person gave the same verdict on the
same answer, weeks apart, blind. This is the ceiling. A judge cannot
meaningfully agree with a human more than the human agrees with themselves; a
judge that appears to is agreeing with noise, and the excess is luck.

**Judge agreement** is measured against round 2. The rubric was written while
looking at round 1, so round 1 is training data and reporting against it would
be marking your own homework.

**Cohen's kappa** because raw agreement flatters a skewed set. If 90% of
answers are correct, a judge that says "correct" every time scores 90% and
knows nothing. Kappa asks how much better than that guess the judge did.

The floor below is declared here, in the repository, before any label existed.
The commit that introduced this file predates the first label file, and that
ordering is the only thing that makes a threshold meaningful.
"""

from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from modelswap import judge, labels, questions

# Declared before labeling. A judge below either line does not get to grade.
MIN_AGREEMENT = 0.85
MIN_KAPPA = 0.60


@dataclass(frozen=True)
class Agreement:
    n: int
    agreed: int
    kappa: float

    @property
    def rate(self) -> float:
        return self.agreed / self.n if self.n else 0.0

    @property
    def clears_floor(self) -> bool:
        return self.rate >= MIN_AGREEMENT and self.kappa >= MIN_KAPPA


def cohens_kappa(pairs: list[tuple[bool, bool]]) -> float:
    """Agreement above what two raters with these habits would hit by chance.

    Returns 0.0 for the degenerate case where both raters said the same thing
    every time: chance agreement is then 1.0 and kappa is undefined. Reporting
    0.0 rather than raising keeps a perfect-but-uninformative run legible, and
    the n and the rate beside it say what happened.
    """
    if not pairs:
        return 0.0
    n = len(pairs)
    observed = sum(1 for a, b in pairs if a == b) / n
    a_true = sum(1 for a, _ in pairs if a) / n
    b_true = sum(1 for _, b in pairs if b) / n
    expected = a_true * b_true + (1 - a_true) * (1 - b_true)
    if expected >= 1.0:
        return 0.0
    return (observed - expected) / (1 - expected)


def agreement_of(pairs: list[tuple[bool, bool]]) -> Agreement:
    return Agreement(
        n=len(pairs),
        agreed=sum(1 for a, b in pairs if a == b),
        kappa=cohens_kappa(pairs),
    )


def self_agreement(root: Path | None = None) -> Agreement:
    """Round 1 against round 2, on the answers labeled in both."""
    first = {label.qid: label for label in labels.read_labels(1, root)}
    second = {label.qid: label for label in labels.read_labels(2, root)}
    shared = sorted(set(first) & set(second))
    return agreement_of([(first[q].correct, second[q].correct) for q in shared])


def judge_agreement(
    round_number: int, variant: str, root: Path | None = None
) -> tuple[Agreement, list[tuple[questions.Question, bool, bool]]]:
    """The judge against one round of labels, plus every case they differed on."""
    by_qid = {q.qid: q for q in questions.load(root).questions}
    pairs: list[tuple[bool, bool]] = []
    disagreements: list[tuple[questions.Question, bool, bool]] = []

    for label in labels.read_labels(round_number, root):
        verdict = judge.read_cached(label.qid, variant, label.sample, label.answer_digest, root)
        if verdict is None:
            continue
        pairs.append((label.correct, verdict.correct))
        if label.correct != verdict.correct:
            disagreements.append((by_qid[label.qid], label.correct, verdict.correct))

    return agreement_of(pairs), disagreements


def report(variant: str, root: Path | None = None) -> int:
    target = len(labels.calibration_set(root))
    round1 = labels.read_labels(1, root)
    round2 = labels.read_labels(2, root)

    print(f"calibration set: {target} answers from {variant}")
    print(f"  round 1: {len(round1)} labeled")
    print(f"  round 2: {len(round2)} labeled\n")

    if not round1:
        print("No labels yet. Run: python -m modelswap.labels --round 1")
        return 1

    if round2:
        ceiling = self_agreement(root)
        print(
            f"self-agreement (the ceiling): {ceiling.rate:.0%}"
            f"  kappa {ceiling.kappa:.2f}  n={ceiling.n}"
        )
    else:
        print("self-agreement: round 2 not labeled, so there is no ceiling to compare against.")
        print("  Judge agreement below is provisional and measured against training data.")

    against = 2 if round2 else 1
    scored, disagreements = judge_agreement(against, variant, root)
    if scored.n == 0:
        print("\nNo judged answers match these labels. Run modelswap.judge first.")
        return 1

    label_source = "round 2 (held out)" if round2 else "round 1 (the rubric was written on it)"
    print(f"\njudge vs {label_source}: {scored.rate:.0%}  kappa {scored.kappa:.2f}  n={scored.n}")
    print(f"  floor: {MIN_AGREEMENT:.0%} agreement and {MIN_KAPPA:.2f} kappa")
    print(f"  {'CLEARS' if scored.clears_floor else 'BELOW'} the floor")

    if disagreements:
        strata = Counter(question.stratum for question, _, _ in disagreements)
        print(f"\n{len(disagreements)} disagreement(s), by stratum:")
        for stratum, count in strata.most_common():
            print(f"  {stratum:14} {count}")
        print("\nwhere the judge and the human differed:")
        for question, human, model in disagreements[:10]:
            print(f"  {question.qid:38} human={human!s:5} judge={model!s:5}")

    if not round2:
        return 1
    return 0 if scored.clears_floor else 1


def main() -> int:
    import argparse  # noqa: PLC0415

    from modelswap import answers  # noqa: PLC0415

    parser = argparse.ArgumentParser(description="Is the judge worth listening to?")
    parser.add_argument("--variant", default="claude-opus-5", choices=answers.VARIANTS)
    args = parser.parse_args()
    return report(args.variant)


if __name__ == "__main__":
    sys.exit(main())
