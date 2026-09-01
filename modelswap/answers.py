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
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from modelswap import corpus, questions
from modelswap.sut import ensure_importable, repo_root

# Every candidate this study knows how to price and run. Kept here rather than
# taken from the command line unchecked, so a typo is a refusal rather than a
# run billed at the wrong rate under a model that does not exist.
VARIANTS = ("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5")


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

    Measured, not guessed: roughly 3,000 input and 150 output tokens per answer
    on this corpus at k=6, taken from real runs. Opus rates, so the estimate
    over-states a Sonnet or Haiku run rather than under-stating it.
    """
    per_answer = 3000 / 1e6 * 5.0 + 150 / 1e6 * 25.0
    return pending * per_answer


def run(variant: str, samples: int, k: int, confirm: bool, root: Path | None = None) -> int:
    ensure_importable()
    from knowledge_desk.config import settings  # noqa: PLC0415
    from knowledge_desk.db import close_pool  # noqa: PLC0415

    from modelswap.tenant import open_scope  # noqa: PLC0415

    if variant not in VARIANTS:
        print(f"unknown variant {variant!r}. Known: {', '.join(VARIANTS)}", file=sys.stderr)
        return 2
    if settings.provider != "real":
        print("mock provider: there is no variance to measure. Refusing.", file=sys.stderr)
        return 1

    loaded_corpus = corpus.load(root)
    loaded_questions = questions.load(root)

    todo = [
        (question, sample)
        for question in loaded_questions.questions
        for sample in range(samples)
        if read_cached(question.qid, variant, sample, loaded_corpus.version, question.text, root)
        is None
    ]
    total = len(loaded_questions) * samples
    print(f"{variant}: {total} answers wanted, {total - len(todo)} cached, {len(todo)} to generate")

    if not todo:
        return 0

    print(f"estimated cost: ${estimate(len(todo)):.2f} (Opus rates, so an upper bound)")
    if not confirm:
        print("pass --confirm to spend it.", file=sys.stderr)
        return 1

    spent = 0.0
    failures = 0
    settings.answer_model = variant
    try:
        scope = open_scope()
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
            marker = "!" if answer.error else "."
            print(marker, end="", flush=True)
            if index % 40 == 0:
                print(f"  {index}/{len(todo)}  ${spent:.2f}", flush=True)
    finally:
        close_pool()

    print(f"\ndone: {len(todo)} generated, {failures} failed, ${spent:.4f} spent")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and cache answers")
    parser.add_argument("--variant", required=True, choices=VARIANTS)
    parser.add_argument("--samples", type=int, default=1, help="answers per question")
    parser.add_argument("-k", type=int, default=6, help="retrieval depth")
    parser.add_argument("--confirm", action="store_true", help="actually spend money")
    args = parser.parse_args()
    return run(args.variant, args.samples, args.k, args.confirm)


if __name__ == "__main__":
    sys.exit(main())
