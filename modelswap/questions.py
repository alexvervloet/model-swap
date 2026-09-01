"""The question set, and whether retrieval can reach what each one needs.

    python -m modelswap.questions              # the stratum report
    python -m modelswap.questions --verify     # probe every question

Questions live in `questions/*.toml`, one file per stratum, named by the file.
A question states what it expects (an answer or a refusal) and which documents
have to be reachable for an answer to be possible at all.

Verification is the part that earns its keep. A question whose sources never
reach the context window measures retrieval, not the model, and would show up
as every candidate failing together. Better to know which ones those are before
spending anything on them.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from modelswap import corpus
from modelswap.sut import repo_root

ANSWERABLE = "answerable"
REFUSAL = "refusal"
EXPECTATIONS = frozenset({ANSWERABLE, REFUSAL})


class QuestionSetError(ValueError):
    """The question set is malformed. Always names the question."""


@dataclass(frozen=True)
class Question:
    qid: str
    stratum: str
    text: str
    expect: str
    sources: tuple[str, ...]
    notes: str

    @property
    def answerable(self) -> bool:
        return self.expect == ANSWERABLE


@dataclass(frozen=True)
class QuestionSet:
    questions: tuple[Question, ...]
    version: str

    def __len__(self) -> int:
        return len(self.questions)

    @property
    def strata(self) -> Counter[str]:
        return Counter(q.stratum for q in self.questions)

    def of_stratum(self, stratum: str) -> tuple[Question, ...]:
        return tuple(q for q in self.questions if q.stratum == stratum)


def questions_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / "questions"


def _parse_file(path: Path, known_documents: frozenset[str]) -> list[Question]:
    # "01-single.toml" -> "single". The number orders the files, the name is
    # the stratum, so adding a stratum is adding a file.
    stratum = path.stem.split("-", 1)[-1]
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    entries = raw.get("question", [])
    if not entries:
        raise QuestionSetError(f"{path.name}: no questions")

    parsed: list[Question] = []
    for entry in entries:
        qid = entry.get("id", "<missing id>")
        expect = entry.get("expect")
        if expect not in EXPECTATIONS:
            raise QuestionSetError(
                f"{qid}: expect must be one of {sorted(EXPECTATIONS)}, got {expect!r}"
            )

        sources = tuple(entry.get("sources", []))
        unknown = [s for s in sources if s not in known_documents]
        if unknown:
            raise QuestionSetError(f"{qid}: names documents not in the corpus: {unknown}")
        if expect == ANSWERABLE and not sources:
            raise QuestionSetError(f"{qid}: an answerable question must name its sources")
        if expect == REFUSAL and sources:
            raise QuestionSetError(f"{qid}: a refusal question cannot have sources")

        parsed.append(
            Question(
                qid=qid,
                stratum=stratum,
                text=entry["text"],
                expect=expect,
                sources=sources,
                notes=entry.get("notes", ""),
            )
        )
    return parsed


def load(root: Path | None = None) -> QuestionSet:
    """Read every stratum file, validate against the corpus, and pin a version."""
    documents = frozenset(d.doc_id for d in corpus.load(root).documents)
    paths = sorted(questions_dir(root).glob("*.toml"))
    if not paths:
        raise FileNotFoundError(f"no question files in {questions_dir(root)}")

    questions: list[Question] = []
    for path in paths:
        questions.extend(_parse_file(path, documents))

    duplicates = [qid for qid, n in Counter(q.qid for q in questions).items() if n > 1]
    if duplicates:
        raise QuestionSetError(f"duplicate question ids: {sorted(duplicates)}")

    fingerprint = hashlib.sha256()
    for question in questions:
        fingerprint.update(question.qid.encode("utf-8"))
        fingerprint.update(question.text.encode("utf-8"))
        fingerprint.update(question.expect.encode("utf-8"))
        fingerprint.update("|".join(question.sources).encode("utf-8"))

    return QuestionSet(questions=tuple(questions), version=fingerprint.hexdigest())


def report() -> int:
    loaded = load()
    print(f"question set {loaded.version[:12]}: {len(loaded)} questions")
    for stratum, count in sorted(loaded.strata.items()):
        answerable = sum(1 for q in loaded.of_stratum(stratum) if q.answerable)
        print(
            f"  {stratum:14} {count:4}   answerable {answerable:3}   refusal {count - answerable:3}"
        )
    return 0


def verify(k: int) -> int:
    """Probe every answerable question and report sources retrieval cannot reach."""
    from knowledge_desk.config import settings  # noqa: PLC0415
    from knowledge_desk.db import close_pool  # noqa: PLC0415

    from modelswap.tenant import embed, open_scope  # noqa: PLC0415

    if settings.provider != "real":
        print("mock embeddings: verification would be meaningless.", file=sys.stderr)
        return 1

    loaded = load()
    print(f"verifying {len(loaded)} questions against retrieval at k={k}\n")
    unreachable: list[tuple[Question, list[str]]] = []
    refusal_noise: list[tuple[Question, float]] = []

    try:
        scope = open_scope()
        for question in loaded.questions:
            hits = scope.search(embed(question.text), k=k)
            found = {Path(hit["path"]).stem for hit in hits}
            if question.answerable:
                missing = [s for s in question.sources if s not in found]
                if missing:
                    unreachable.append((question, missing))
            elif hits:
                # Not a failure. A refusal question that retrieves something
                # close is a harder refusal, and worth seeing.
                refusal_noise.append((question, float(hits[0]["distance"])))
    finally:
        close_pool()

    if unreachable:
        print(f"{len(unreachable)} answerable question(s) cannot reach a named source at k={k}:")
        for question, missing in unreachable:
            print(f"  {question.qid:38} missing {missing}")
    else:
        print(f"every answerable question reaches its sources at k={k}")

    if refusal_noise:
        closest = sorted(refusal_noise, key=lambda pair: pair[1])[:5]
        print("\nclosest retrieval for a refusal question (lower is a harder refusal):")
        for question, distance in closest:
            print(f"  {distance:.4f}  {question.qid}")

    return 1 if unreachable else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="The question set and its coverage")
    parser.add_argument("--verify", action="store_true", help="probe retrieval for every question")
    parser.add_argument("-k", type=int, default=6, help="retrieval depth to verify against")
    args = parser.parse_args()
    return verify(args.k) if args.verify else report()


if __name__ == "__main__":
    sys.exit(main())
