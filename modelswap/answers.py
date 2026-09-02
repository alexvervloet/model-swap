"""Generate answers, once, and keep them.

    python -m modelswap.answers --variant claude-sonnet-5 --samples 3

Generation is the only part that costs money, so it happens once and lands on
disk. Rescoring a cached run against a new rubric is free and offline, which is
what makes the judge iterable at all.

A cached answer records the corpus version, the question text and the model it
came from. A cache entry whose question text has since changed is a miss, not a
hit: the id stayed the same, the thing asked did not.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from modelswap import corpus, ledger, questions
from modelswap.sut import ensure_importable, repo_root

# Every candidate this study knows how to price and run. Kept here rather than
# taken from the command line unchecked, so a typo is a refusal rather than a
# run billed at the wrong rate under a model that does not exist.
#
# Opus is deliberately absent. At $5/$25 per million tokens it is five times
# Sonnet's input price, and one exploratory afternoon on it cost more than this
# project's whole budget. The comparison that matters to a real migration is
# the one where somebody is trying to spend less, and that is Sonnet against
# Haiku.
VARIANTS = ("claude-sonnet-5", "claude-haiku-4-5")

# Models whose answers are already on disk and paid for, and which will never be
# generated again. Opus produced a full pass before it was dropped as too
# expensive; those 120 answers cost $2.60 and throwing them away would not
# refund a penny. They are readable, gradeable, and reportable as a reference
# arm, and they are not candidates: nothing here can spend money on them.
REFERENCE_VARIANTS = ("claude-opus-5",)

# Anything a reader may look at, whether or not a writer may produce it.
READABLE = VARIANTS + REFERENCE_VARIANTS

# A hard ceiling per run, in dollars. A run that wants more than this is a
# mistake rather than an ambition, and it should say so before spending rather
# than after. Raise it deliberately with --max-spend, never by editing this.
MAX_SPEND_USD = 1.50


@dataclass(frozen=True)
class Answer:
    qid: str
    variant: str
    sample: int
    question: str
    text: str
    sources: list[str]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    seconds: float
    corpus_version: str
    error: str | None = None


def cache_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / "cache" / "answers"


def _path(root: Path | None, corpus_version: str, variant: str, sample: int, qid: str) -> Path:
    return cache_dir(root) / corpus_version[:12] / variant / f"s{sample}" / f"{qid}.json"


def read_cached(
    qid: str,
    variant: str,
    sample: int,
    corpus_version: str,
    question: str,
    root: Path | None = None,
) -> Answer | None:
    """A hit only if the question text still matches what was answered."""
    path = _path(root, corpus_version, variant, sample, qid)
    if not path.is_file():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("question") != question:
        return None
    if record.get("error"):
        # A failure is kept on disk to be read, never treated as an answer. It
        # cost nothing to produce and scoring it would count an outage as the
        # model's fault. The next run regenerates it.
        return None
    return Answer(**record)


def iter_cached(root: Path | None = None) -> Iterator[Answer]:
    """Every successful cached answer, whatever variant or corpus produced it.

    Errored records are skipped here for the same reason `read_cached` refuses
    them: they are kept to be read by a person, never counted as output.
    """
    base = cache_dir(root)
    if not base.is_dir():
        return
    for path in sorted(base.rglob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("error"):
            continue
        yield Answer(**record)


def write_cached(answer: Answer, root: Path | None = None) -> None:
    path = _path(root, answer.corpus_version, answer.variant, answer.sample, answer.qid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(answer), indent=2, sort_keys=True), encoding="utf-8")


def generate_one(scope: Any, question: questions.Question, k: int) -> dict[str, Any]:
    """Drive the real assistant and collect what it produced."""
    from knowledge_desk import assistant  # noqa: PLC0415

    text: list[str] = []
    sources: list[str] = []
    usage: dict[str, Any] = {}
    error: str | None = None

    started = time.monotonic()
    for event in assistant.answer_stream(scope, question.text, k):
        kind = event["type"]
        if kind == "token":
            text.append(event["text"])
        elif kind == "sources":
            sources = [Path(s["path"]).stem for s in event["sources"]]
        elif kind == "done":
            usage = event
        elif kind == "error":
            error = event["message"]
    seconds = time.monotonic() - started

    return {
        "text": "".join(text).strip(),
        "sources": sources,
        "input_tokens": usage.get("usage", {}).get("input_tokens", 0),
        "output_tokens": usage.get("usage", {}).get("output_tokens", 0),
        "cost_usd": usage.get("cost_usd", 0.0),
        "seconds": seconds,
        "error": error,
    }


def estimate(pending: int) -> float:
    """Rough dollars for the answers still to generate.

    Measured, not guessed: roughly 3,000 input and 200 output tokens per answer
    on this corpus at k=6, taken from 240 real ones. Priced at Sonnet, the
    dearest model still in play, so the number shown before spending is never
    lower than what gets spent.
    """
    per_answer = 3000 / 1e6 * 2.0 + 200 / 1e6 * 10.0
    return pending * per_answer


def run(
    variant: str,
    samples: int,
    k: int,
    confirm: bool,
    max_spend: float = MAX_SPEND_USD,
    root: Path | None = None,
) -> int:
    ensure_importable()
    from knowledge_desk.config import settings  # noqa: PLC0415
    from knowledge_desk.db import close_pool  # noqa: PLC0415

    from modelswap import tenant  # noqa: PLC0415
    from modelswap.tenant import open_scope  # noqa: PLC0415

    if variant not in VARIANTS:
        print(f"unknown variant {variant!r}. Known: {', '.join(VARIANTS)}", file=sys.stderr)
        return 2
    if settings.provider != "real":
        print("mock provider: there is no variance to measure. Refusing.", file=sys.stderr)
        return 1

    loaded_corpus = corpus.load(root)
    loaded_questions = questions.load(root)

    # Before the estimate, not after the spend: an index built by something
    # other than this project's loader retrieves passages unrelated to the
    # question and says nothing about it. See LESSONS 9.
    scope = open_scope()
    try:
        problem = tenant.verify_index(loaded_corpus.version, scope.org_id, root)
        if problem:
            print(f"refusing to generate: {problem}", file=sys.stderr)
            return 1

        todo = [
            (question, sample)
            for question in loaded_questions.questions
            for sample in range(samples)
            if read_cached(
                question.qid, variant, sample, loaded_corpus.version, question.text, root
            )
            is None
        ]
        total = len(loaded_questions) * samples
        print(
            f"{variant}: {total} answers wanted, {total - len(todo)} cached,"
            f" {len(todo)} to generate"
        )
        if not todo:
            return 0

        projected = estimate(len(todo))
        print(f"estimated cost: ${projected:.2f} (Sonnet rates, so an upper bound)")
        print(f"  budget: {ledger.summary(root)}")
        blocked = ledger.headroom_for(projected, root)
        if blocked:
            print(f"refusing: {blocked}", file=sys.stderr)
            return 1
        if projected > max_spend:
            print(
                f"refusing: ${projected:.2f} is over the ${max_spend:.2f} ceiling."
                " Use fewer samples, or raise it deliberately with --max-spend.",
                file=sys.stderr,
            )
            return 1
        if not confirm:
            print("pass --confirm to spend it.", file=sys.stderr)
            return 1

        spent = 0.0
        failures = 0
        settings.answer_model = variant
        for index, (question, sample) in enumerate(todo, start=1):
            result = generate_one(scope, question, k)
            answer = Answer(
                qid=question.qid,
                variant=variant,
                sample=sample,
                question=question.text,
                corpus_version=loaded_corpus.version,
                **result,
            )
            write_cached(answer, root)
            spent += answer.cost_usd
            if answer.error:
                failures += 1
            print("!" if answer.error else ".", end="", flush=True)
            if spent > max_spend:
                # The estimate was wrong, which is the case a ceiling exists
                # for. Everything generated so far is cached, so stopping here
                # loses nothing and the next run resumes.
                print(
                    f"\n\nstopping at ${spent:.2f}: over the ${max_spend:.2f} ceiling"
                    f" after {index} of {len(todo)}. Answers so far are cached.",
                    file=sys.stderr,
                )
                break
            if index % 40 == 0:
                print(f"  {index}/{len(todo)}  ${spent:.2f}", flush=True)
    finally:
        close_pool()

    ledger.record("answers", variant, len(todo), spent, root)
    print(f"\ndone: {len(todo)} generated, {failures} failed, ${spent:.4f} spent")
    print(f"  budget: {ledger.summary(root)}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and cache answers")
    parser.add_argument("--variant", required=True, choices=VARIANTS)
    parser.add_argument("--samples", type=int, default=1, help="answers per question")
    parser.add_argument("-k", type=int, default=6, help="retrieval depth")
    parser.add_argument("--confirm", action="store_true", help="actually spend money")
    parser.add_argument(
        "--max-spend",
        type=float,
        default=MAX_SPEND_USD,
        help=f"dollars this run may spend before it stops (default {MAX_SPEND_USD})",
    )
    args = parser.parse_args()
    return run(args.variant, args.samples, args.k, args.confirm, args.max_spend)


if __name__ == "__main__":
    sys.exit(main())
