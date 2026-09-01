"""What each model costs, how long it takes, and how often it is right.

    python -m modelswap.compare

Reads the cache and nothing else. No API calls, no database, no key, no money:
every number here was paid for once and is now free to recompute as often as
you like. That is the point of caching generation rather than the convenience.

Quality is only shown for variants whose answers have been graded under the
current rubric. A variant with answers and no verdicts shows its cost and its
latency, which are facts about the run rather than about the rubric.
"""

from __future__ import annotations

import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from modelswap import answers, judge, questions


@dataclass(frozen=True)
class Row:
    variant: str
    n: int
    total_cost: float
    input_tokens: float
    output_tokens: float
    p50_seconds: float
    p95_seconds: float
    graded: int
    correct: int

    @property
    def reference_only(self) -> bool:
        return self.variant in answers.REFERENCE_VARIANTS

    @property
    def accuracy(self) -> float | None:
        return self.correct / self.graded if self.graded else None

    @property
    def cost_per_hundred(self) -> float:
        return self.total_cost / self.n * 100 if self.n else 0.0


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(int(len(ordered) * fraction), len(ordered) - 1)
    return ordered[index]


def collect(root: Path | None = None) -> list[Row]:
    by_variant: dict[str, list[answers.Answer]] = defaultdict(list)
    for answer in answers.iter_cached(root):
        by_variant[answer.variant].append(answer)

    rows: list[Row] = []
    for variant, records in by_variant.items():
        graded = correct = 0
        for answer in records:
            verdict = judge.read_cached(
                answer.qid, variant, answer.sample, judge.digest(answer.text), root
            )
            if verdict is not None:
                graded += 1
                correct += int(verdict.correct)
        rows.append(
            Row(
                variant=variant,
                n=len(records),
                total_cost=sum(a.cost_usd for a in records),
                input_tokens=statistics.mean(a.input_tokens for a in records),
                output_tokens=statistics.mean(a.output_tokens for a in records),
                p50_seconds=_percentile([a.seconds for a in records], 0.5),
                p95_seconds=_percentile([a.seconds for a in records], 0.95),
                graded=graded,
                correct=correct,
            )
        )
    return sorted(rows, key=lambda row: row.total_cost)


def by_stratum(root: Path | None = None) -> dict[str, dict[str, tuple[int, int]]]:
    """Correct-out-of-graded per variant per stratum, for the variants graded.

    The overall rate hides the thing worth knowing. Two models at 95% are not
    the same model if one of them is losing its five points on refusals.
    """
    strata = {q.qid: q.stratum for q in questions.load(root).questions}
    tally: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))

    for answer in answers.iter_cached(root):
        verdict = judge.read_cached(
            answer.qid, answer.variant, answer.sample, judge.digest(answer.text), root
        )
        if verdict is None:
            continue
        cell = tally[answer.variant][strata[answer.qid]]
        cell[1] += 1
        cell[0] += int(verdict.correct)

    return {
        variant: {stratum: (cell[0], cell[1]) for stratum, cell in per_stratum.items()}
        for variant, per_stratum in tally.items()
    }


def report(root: Path | None = None) -> int:
    rows = collect(root)
    if not rows:
        print("no cached answers. Run modelswap.answers first.")
        return 1

    width = max(len(row.variant) + 13 for row in rows)
    print(
        f"{'variant':{width}}{'n':>4}{'$/100':>8}{'in':>7}{'out':>6}"
        f"{'p50s':>7}{'p95s':>7}{'correct':>12}"
    )
    for row in rows:
        accuracy = f"{row.correct}/{row.graded}" if row.graded else "ungraded"
        marker = " (reference)" if row.reference_only else ""
        print(
            f"{row.variant + marker:{width}}{row.n:>4}{row.cost_per_hundred:>8.2f}"
            f"{row.input_tokens:>7.0f}{row.output_tokens:>6.0f}"
            f"{row.p50_seconds:>7.1f}{row.p95_seconds:>7.1f}{accuracy:>12}"
        )

    cheapest = rows[0]
    dearest = rows[-1]
    if cheapest is not dearest and cheapest.total_cost:
        ratio = dearest.total_cost / cheapest.total_cost
        print(
            f"\n{dearest.variant} costs {ratio:.1f}x {cheapest.variant} for the same"
            f" {cheapest.n} questions, and is {dearest.p50_seconds / cheapest.p50_seconds:.1f}x"
            " slower at the median."
        )

    graded = by_stratum(root)
    if len(graded) > 1:
        strata = sorted({s for m in graded.values() for s in m})
        variants = sorted(graded)
        print(f"\n{'stratum':16}" + "".join(f"{v.replace('claude-', ''):>16}" for v in variants))
        for stratum in strata:
            line = f"{stratum:16}"
            for variant in variants:
                ok, total = graded[variant].get(stratum, (0, 0))
                line += f"{(f'{ok}/{total}' if total else '-'):>16}"
            print(line)

    ungraded = [row.variant for row in rows if not row.graded]
    if ungraded:
        print(f"\nungraded: {', '.join(ungraded)}. Run modelswap.judge to fill them in.")
    return 0


def main() -> int:
    return report()


if __name__ == "__main__":
    sys.exit(main())
