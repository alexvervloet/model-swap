"""Two judges over the same answers.

    python -m modelswap.judges

An earlier version of this project graded 170 answers with a Claude Opus judge
before the whole thing moved down a tier. Those verdicts are still on disk under
the retired rubric's hash, and they are worth more than the answers they graded.

Grading the same answers with the current judge produces something this project
otherwise had no way to obtain: two independent judges over one identical set of
outputs. That measures the instrument rather than the thing being measured, and
it is the only handle available on the bias the current setup carries, which is
that the judge is also one of the two candidates.

**What the difference-in-differences shows.** If the retired Opus judge was more
generous to Opus's answers than the current Sonnet judge was, *and* the two
judges agreed more closely on Haiku's answers, that gap is evidence of a judge
preferring its own family's output. If both judges differ by about the same
amount on both models' answers, that is a judge being systematically stricter or
softer, which is a calibration offset rather than a preference and does not
threaten a paired comparison.

**What it does not show.** 170 items is not much, one of the two variants has
only 50 of them, and those 50 are the first 50 in file order rather than a
sample, so they carry three of the six strata. This is a signal worth reporting
with its limits attached, not a finding.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from modelswap import agreement, answers, judge


@dataclass(frozen=True)
class Pairing:
    variant: str
    scored: agreement.Agreement
    archived_correct: int
    current_correct: int

    @property
    def archived_rate(self) -> float:
        return self.archived_correct / self.scored.n if self.scored.n else 0.0

    @property
    def current_rate(self) -> float:
        return self.current_correct / self.scored.n if self.scored.n else 0.0

    @property
    def generosity_gap(self) -> float:
        """How much more often the retired judge said correct than the current
        one. Positive means the retired judge was the softer of the two."""
        return self.archived_rate - self.current_rate


def pair_up(archived_rubric: str, root: Path | None = None) -> list[Pairing]:
    """Every answer graded under both rubrics, grouped by the model that wrote it."""
    by_variant: dict[str, list[tuple[bool, bool]]] = {}
    for answer in answers.iter_cached(root):
        digest = judge.digest(answer.text)
        old = judge.read_cached(
            answer.qid, answer.variant, answer.sample, digest, root, rubric=archived_rubric
        )
        new = judge.read_cached(answer.qid, answer.variant, answer.sample, digest, root)
        if old is None or new is None:
            continue
        by_variant.setdefault(answer.variant, []).append((old.correct, new.correct))

    return [
        Pairing(
            variant=variant,
            scored=agreement.agreement_of(pairs),
            archived_correct=sum(1 for old, _ in pairs if old),
            current_correct=sum(1 for _, new in pairs if new),
        )
        for variant, pairs in sorted(by_variant.items())
    ]


def archived_judge_model(archived_rubric: str, root: Path | None = None) -> str:
    """Which model produced the archived verdicts, if the records say."""
    for answer in answers.iter_cached(root):
        found = judge.read_cached(
            answer.qid,
            answer.variant,
            answer.sample,
            judge.digest(answer.text),
            root,
            rubric=archived_rubric,
        )
        if found is not None:
            return found.judge_model or "unrecorded"
    return "unrecorded"


def report(root: Path | None = None) -> int:
    archived = judge.archived_rubrics(root)
    if not archived:
        print("no retired rubrics on disk. Nothing to compare the judge against.")
        return 1

    exit_code = 1
    for rubric in archived:
        who = archived_judge_model(rubric, root)
        pairings = pair_up(rubric, root)
        print(f"rubric {rubric} ({who})  vs  {judge.RUBRIC_VERSION[:12]} ({judge.JUDGE_MODEL})")
        if not pairings:
            print(
                "  no answer is graded under both. Run modelswap.judge to fill the current one.\n"
            )
            continue

        exit_code = 0
        print(
            f"\n  {'answers by':22}{'n':>4}{'agree':>8}{'kappa':>8}{'retired':>10}{'current':>10}"
        )
        for pairing in pairings:
            print(
                f"  {pairing.variant:22}{pairing.scored.n:>4}"
                f"{pairing.scored.rate:>8.0%}{pairing.scored.kappa:>8.2f}"
                f"{pairing.archived_rate:>10.0%}{pairing.current_rate:>10.0%}"
            )

        gaps = {p.variant: p.generosity_gap for p in pairings if p.scored.n}
        if len(gaps) > 1:
            print("\n  how much softer the retired judge was, per model's answers:")
            for variant, gap in sorted(gaps.items(), key=lambda item: -item[1]):
                print(f"    {variant:22}{gap:+.0%}")
            spread = max(gaps.values()) - min(gaps.values())
            print(
                f"\n  spread: {spread:.0%}. A large spread favouring the retired judge's own"
                "\n  family is self-preference. A small one is a calibration offset, which"
                "\n  a paired comparison cancels."
            )
        print()

    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two judges over the same answers")
    parser.parse_args()
    return report()


if __name__ == "__main__":
    sys.exit(main())
