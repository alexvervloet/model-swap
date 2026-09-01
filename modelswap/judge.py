"""Grade an answer against the corpus, with a rubric that can be argued with.

    python -m modelswap.judge --variant claude-opus-5 --samples 1 --confirm

The judge is a model, so it is a measuring instrument with its own error. It
gets calibrated against human labels before anything it says is trusted; see
`modelswap.labels` and `modelswap.agreement`. Nothing here reports a score on
its own.

Three deliberate choices:

**Reference-based, not open-ended.** Every question carries the correct answer
in its `notes`, written when the question was written. Asking "is this right"
with the answer in hand is a far easier task than asking a model to know the
corpus, and an easier task has less judge error in it.

**Reasoning before verdict.** The fields are ordered so the free text is
generated first. A model that states its verdict first spends the rest of the
response defending it. This is borrowed from good-news-feed, where putting the
reason before the number erased a scoring bias across two model families.

**Blind to the candidate.** The judge is never told which model produced the
answer, so it cannot prefer a name. It cannot be blinded to the writing style
of its own family, which is the bias that survives and gets measured rather
than claimed away.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from modelswap import answers, corpus, questions
from modelswap.sut import ensure_importable, repo_root

JUDGE_MODEL = "claude-opus-5"

RUBRIC = """\
You are grading one answer produced by a document-grounded assistant for a \
ferry operator. You are given the question, what the documents actually say, \
and the answer.

Decide two things.

behaviour: did the answer ANSWER the question, or REFUSE it? A refusal says the \
documents do not cover this, or otherwise declines to answer. An answer that \
hedges but still states a position has ANSWERED.

correct: is the answer right?
- If the expected behaviour is a refusal, the answer is correct only when it \
refuses. An invented but plausible policy is the worst outcome here, not a \
partial credit case.
- If the expected behaviour is an answer, the answer is correct when it states \
what the reference says. It may add detail, caveats or citations. It is \
incorrect if it contradicts the reference, states the opposite conclusion, \
omits the part the question actually asked for, or refuses.
- Tone, length, and formatting are not part of correctness. A blunt correct \
answer and a wordy correct answer are both correct.

Write your reasoning first, in one or two sentences, then the two fields."""

# Every input that changes what a verdict means. A rubric edit invalidates every
# cached judgment rather than silently mixing two rubrics in one reported score.
RUBRIC_VERSION = hashlib.sha256((RUBRIC + JUDGE_MODEL).encode("utf-8")).hexdigest()

CITATION = re.compile(r"\[\d+\]")


class Verdict(BaseModel):
    """Field order is generation order. Reasoning first, on purpose."""

    reasoning: str
    behaviour: Literal["answered", "refused"]
    correct: bool


@dataclass(frozen=True)
class Judgment:
    qid: str
    variant: str
    sample: int
    correct: bool
    behaviour: str
    expected_behaviour: str
    behaviour_matches: bool
    cited: bool
    reasoning: str
    rubric_version: str
    answer_digest: str

    @property
    def metrics(self) -> dict[str, bool]:
        """The metric family. One error budget is spent across all of these."""
        return {
            "correct": self.correct,
            "behaviour_matches": self.behaviour_matches,
            "cited": self.cited,
        }


def cache_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / "cache" / "judgments"


def _path(root: Path | None, variant: str, sample: int, qid: str) -> Path:
    return cache_dir(root) / RUBRIC_VERSION[:12] / variant / f"s{sample}" / f"{qid}.json"


def read_cached(
    qid: str, variant: str, sample: int, answer_digest: str, root: Path | None = None
) -> Judgment | None:
    path = _path(root, variant, sample, qid)
    if not path.is_file():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("answer_digest") != answer_digest:
        return None
    return Judgment(**record)


def write_cached(judgment: Judgment, root: Path | None = None) -> None:
    path = _path(root, judgment.variant, judgment.sample, judgment.qid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(judgment), indent=2, sort_keys=True), encoding="utf-8")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def has_citation(text: str) -> bool:
    """A `[n]` marker minted by the app, not something the answer can invent."""
    return CITATION.search(text) is not None


def build_prompt(question: questions.Question, answer_text: str) -> str:
    expected = "a refusal" if question.expect == questions.REFUSAL else "an answer"
    reference = question.notes or "(none recorded)"
    return (
        f"QUESTION\n{question.text}\n\n"
        f"EXPECTED BEHAVIOUR\n{expected}\n\n"
        f"WHAT THE DOCUMENTS SAY\n{reference}\n\n"
        f"ANSWER TO GRADE\n{answer_text}"
    )


def judge_one(client: Any, question: questions.Question, answer_text: str) -> Verdict:
    response = client.messages.parse(
        model=JUDGE_MODEL,
        max_tokens=1024,
        system=RUBRIC,
        messages=[{"role": "user", "content": build_prompt(question, answer_text)}],
        output_format=Verdict,
    )
    parsed: Verdict = response.parsed_output
    return parsed


def to_judgment(question: questions.Question, answer: answers.Answer, verdict: Verdict) -> Judgment:
    expected = "refused" if question.expect == questions.REFUSAL else "answered"
    return Judgment(
        qid=question.qid,
        variant=answer.variant,
        sample=answer.sample,
        correct=verdict.correct,
        behaviour=verdict.behaviour,
        expected_behaviour=expected,
        behaviour_matches=verdict.behaviour == expected,
        # A refusal has nothing to cite, so citation is only asked of answers.
        cited=has_citation(answer.text) if expected == "answered" else True,
        reasoning=verdict.reasoning,
        rubric_version=RUBRIC_VERSION,
        answer_digest=digest(answer.text),
    )


def estimate(pending: int) -> float:
    """Judging is not free and is easy to forget in a budget.

    About 400 input and 120 output tokens per verdict, at Opus rates.
    """
    return pending * (400 / 1e6 * 5.0 + 120 / 1e6 * 25.0)


def run(variant: str, samples: int, confirm: bool, root: Path | None = None) -> int:
    ensure_importable()
    from knowledge_desk.config import settings  # noqa: PLC0415

    if settings.provider != "real":
        print("no key: the judge is a model. Refusing.", file=sys.stderr)
        return 1

    corpus_version = corpus.load(root).version
    loaded = questions.load(root)

    todo: list[tuple[questions.Question, answers.Answer]] = []
    missing = 0
    for question in loaded.questions:
        for sample in range(samples):
            answer = answers.read_cached(
                question.qid, variant, sample, corpus_version, question.text, root
            )
            if answer is None:
                missing += 1
                continue
            if read_cached(question.qid, variant, sample, digest(answer.text), root) is None:
                todo.append((question, answer))

    if missing:
        print(f"{missing} answer(s) not generated yet; run modelswap.answers first.")
    print(f"{len(todo)} verdict(s) to produce")
    if not todo:
        return 0

    print(f"estimated cost: ${estimate(len(todo)):.2f}")
    if not confirm:
        print("pass --confirm to spend it.", file=sys.stderr)
        return 1

    import anthropic  # noqa: PLC0415

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    for index, (question, answer) in enumerate(todo, start=1):
        verdict = judge_one(client, question, answer.text)
        write_cached(to_judgment(question, answer, verdict), root)
        print("." if verdict.correct else "x", end="", flush=True)
        if index % 40 == 0:
            print(f"  {index}/{len(todo)}", flush=True)
    print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Grade cached answers")
    parser.add_argument("--variant", required=True, choices=answers.VARIANTS)
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    return run(args.variant, args.samples, args.confirm)


if __name__ == "__main__":
    sys.exit(main())
