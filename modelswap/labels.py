"""Human labels, which are the only ground truth here.

    python -m modelswap.labels --round 1      # label the calibration set
    python -m modelswap.labels --round 2      # again, later, blind to round 1
    python -m modelswap.labels --status

The judge is a model grading a model. Nothing it says means anything until it
has been checked against a person, and this is where the person's answers go.

**Two rounds, blind.** A single annotator has no inter-annotator agreement to
report, so the substitute is agreement with yourself: label the same answers
twice, some days apart, without seeing the first round. That number is the
ceiling. A judge cannot meaningfully agree with you more than you agree with
yourself, and a judge that appears to is being measured against noise.

**Round 2 shows nothing from round 1.** Not the label, not whether an item was
labeled, not the order. Seeing your earlier verdict does not test recall, it
tests anchoring.

Labels are committed. They are slow to produce, they do not regenerate, and a
scored run means nothing without them.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from modelswap import answers, corpus, judge, questions
from modelswap.sut import repo_root

# Fixed: the calibration set has to be the same set every round and every
# session, or the two rounds are not measuring the same thing.
CALIBRATION_SEED = 20260901
PER_STRATUM = 7


@dataclass(frozen=True)
class Label:
    qid: str
    variant: str
    sample: int
    answer_digest: str
    correct: bool
    behaviour: str
    round: int
    labeled_at: str


def labels_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / "labels"


def labels_path(round_number: int, root: Path | None = None) -> Path:
    return labels_dir(root) / f"round{round_number}.jsonl"


def read_labels(round_number: int, root: Path | None = None) -> list[Label]:
    path = labels_path(round_number, root)
    if not path.is_file():
        return []
    return [
        Label(**json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def append_label(label: Label, root: Path | None = None) -> None:
    """One line, flushed immediately. Labeling is long and gets interrupted."""
    path = labels_path(label.round, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(label), sort_keys=True) + "\n")


def calibration_set(root: Path | None = None) -> tuple[questions.Question, ...]:
    """A fixed, stratified sample of the question set.

    Stratified rather than random over the whole set, because the strata are
    not equally hard and a judge that agrees on lookups while missing every
    refusal would average out to something that looks fine.
    """
    loaded = questions.load(root)
    # S311: determinism is the requirement, not unpredictability. The same 42
    # answers have to come out on every machine and in both rounds.
    rng = random.Random(CALIBRATION_SEED)  # noqa: S311
    chosen: list[questions.Question] = []
    for stratum in sorted(loaded.strata):
        pool = sorted(loaded.of_stratum(stratum), key=lambda q: q.qid)
        chosen.extend(rng.sample(pool, min(PER_STRATUM, len(pool))))
    return tuple(sorted(chosen, key=lambda q: q.qid))


def _prompt(text: str, valid: dict[str, str]) -> str | None:
    """Read one keystroke-ish answer. Returns None to stop the session."""
    options = "/".join(valid)
    while True:
        try:
            reply = input(f"{text} [{options}, or q to stop]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if reply == "q":
            return None
        if reply in valid:
            return valid[reply]
        print(f"  not one of {options}")


def label_session(round_number: int, variant: str, root: Path | None = None) -> int:
    corpus_version = corpus.load(root).version
    already = {label.qid for label in read_labels(round_number, root)}
    pending = [q for q in calibration_set(root) if q.qid not in already]

    if not pending:
        print(f"round {round_number}: nothing left to label.")
        return 0

    print(f"round {round_number}: {len(pending)} of {len(calibration_set(root))} left\n")
    print("You are grading the ANSWER against WHAT THE DOCUMENTS SAY.")
    print("Tone and length are not part of correctness. Ctrl-C or q stops; progress is kept.\n")

    for number, question in enumerate(pending, start=1):
        answer = answers.read_cached(question.qid, variant, 0, corpus_version, question.text, root)
        if answer is None:
            print(f"  skipping {question.qid}: no cached answer")
            continue

        expected = "a refusal" if question.expect == questions.REFUSAL else "an answer"
        print("=" * 72)
        print(f"[{number}/{len(pending)}]  {question.stratum}")
        print(f"\nQUESTION\n  {question.text}")
        print(f"\nEXPECTED\n  {expected}")
        print(f"\nWHAT THE DOCUMENTS SAY\n  {question.notes}")
        print(f"\nANSWER\n  {answer.text}\n")

        behaviour = _prompt("Did it answer or refuse?", {"a": "answered", "r": "refused"})
        if behaviour is None:
            break
        correct = _prompt("Is it correct?", {"y": "yes", "n": "no"})
        if correct is None:
            break

        append_label(
            Label(
                qid=question.qid,
                variant=variant,
                sample=0,
                answer_digest=judge.digest(answer.text),
                correct=correct == "yes",
                behaviour=behaviour,
                round=round_number,
                labeled_at=datetime.now(UTC).isoformat(timespec="seconds"),
            ),
            root,
        )
        print()

    remaining = len(calibration_set(root)) - len(read_labels(round_number, root))
    print(f"\nsaved. {remaining} left in round {round_number}.")
    return 0


def status(root: Path | None = None) -> int:
    target = calibration_set(root)
    print(f"calibration set: {len(target)} answers, stratified {PER_STRATUM} per stratum")
    for round_number in (1, 2):
        labels = read_labels(round_number, root)
        print(f"  round {round_number}: {len(labels)}/{len(target)} labeled")
    if len(read_labels(2, root)) == len(target) == len(read_labels(1, root)):
        print("\nboth rounds complete: run python -m modelswap.agreement")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Label the calibration set by hand")
    parser.add_argument("--round", type=int, choices=(1, 2), help="which labeling round")
    parser.add_argument("--variant", default="claude-opus-5", choices=answers.VARIANTS)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.status or args.round is None:
        return status()
    return label_session(args.round, args.variant)


if __name__ == "__main__":
    sys.exit(main())
