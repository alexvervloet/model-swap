"""Ask what retrieval returns for a question, without generating an answer.

    python -m modelswap.probe "can I take a dog to Rensley Point?"

Authoring a question means knowing whether the passage that answers it is
reachable at all. A question the retriever cannot reach measures the retriever,
not the model, and a question whose answer arrives in every top-k measures
nothing. This is how each one gets checked before it goes in the set.
"""

from __future__ import annotations

import argparse
import sys

from modelswap.sut import ensure_importable
from modelswap.tenant import embed, open_scope


def probe(question: str, k: int = 6) -> int:
    ensure_importable()
    from knowledge_desk.config import settings  # noqa: PLC0415
    from knowledge_desk.db import close_pool  # noqa: PLC0415

    if settings.provider != "real":
        print("mock embeddings: these results are noise, not retrieval.", file=sys.stderr)

    try:
        scope = open_scope()
        hits = scope.search(embed(question), k=k)
        print(f"{question}\n")
        for rank, hit in enumerate(hits, start=1):
            snippet = " ".join(hit["text"].split())[:96]
            print(f"  {rank}. {hit['distance']:.4f}  {hit['path']:34} #{hit['ordinal']}")
            print(f"      {snippet}...")
    finally:
        close_pool()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Show what retrieval returns for a question")
    parser.add_argument("question")
    parser.add_argument("-k", type=int, default=6, help="how many chunks to fetch")
    args = parser.parse_args()
    return probe(args.question, args.k)


if __name__ == "__main__":
    sys.exit(main())
