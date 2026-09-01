"""Load the corpus into the system under test.

    python -m modelswap.load                # refuses unless embeddings are real
    python -m modelswap.load --mock         # index anyway, and say so loudly
    python -m modelswap.load --reset        # delete the tenant first and re-embed

Creates the Meridian tenant if it is missing, reconciles its documents against
`corpus/meridian/`, and drains the ingest queue so everything is embedded and
retrievable before anything tries to measure it.

Idempotent, and that is a trap worth knowing about: knowledge-desk reconciles on
content hash, so an unchanged document is not re-embedded. Switching from mock
embeddings to real ones changes no content and therefore re-embeds nothing.
`--reset` is the way out.
"""

from __future__ import annotations

import argparse
import sys

from modelswap import corpus, database
from modelswap.sut import ensure_importable

ORG_SLUG = "meridian"
ORG_NAME = "Meridian Ferries"
OWNER_EMAIL = "owner@meridian.test"

# S105: a throwaway login for a local demo tenant, matching the seed data in
# the system under test. Nothing here reaches a deployment.
OWNER_PASSWORD = "demo-password-123"  # noqa: S105

SOURCE = "model-swap-corpus"

MOCK_BANNER = """
  ################################################################
  #  MOCK EMBEDDINGS. Retrieval over this index is meaningless.   #
  #  Every vector is a deterministic fake, so which passages come #
  #  back has nothing to do with what the question asked. Fine    #
  #  for exercising the pipeline. Not something to score.         #
  #  Set VOYAGE_API_KEY and re-run with --reset.                  #
  ################################################################
"""


def load(*, allow_mock: bool = False, reset: bool = False) -> int:
    ensure_importable()
    from knowledge_desk import accounts, ingest, migrate  # noqa: PLC0415
    from knowledge_desk.config import settings  # noqa: PLC0415
    from knowledge_desk.db import close_pool, connect  # noqa: PLC0415

    # Our own database, created and migrated here rather than by a README step
    # somebody can skip. See modelswap.database for why it is not shared.
    if database.create():
        print(f"  created database {database.DB_NAME}")
    applied = migrate.apply_pending()
    if applied:
        print(f"  applied {len(applied)} migration(s)")
    migrate.ensure_app_role()

    mock = settings.provider != "real"
    if mock and not allow_mock:
        print("refusing to index with mock embeddings.", file=sys.stderr)
        print(MOCK_BANNER, file=sys.stderr)
        print("  Pass --mock to index anyway, knowing the index cannot be scored.", file=sys.stderr)
        return 1

    loaded = corpus.load()
    print(f"corpus {loaded.version[:12]}: {len(loaded)} documents, {loaded.words} words")
    if mock:
        print(MOCK_BANNER)

    try:
        with connect() as conn:
            row = conn.execute("select id from orgs where slug = %s", (ORG_SLUG,)).fetchone()

        if row is not None and reset:
            accounts.delete_org(row["id"])
            print(f"  deleted tenant {ORG_SLUG}")
            row = None

        if row is None:
            ctx = accounts.create_org_with_owner(ORG_SLUG, ORG_NAME, OWNER_EMAIL, OWNER_PASSWORD)
            org_id = ctx.org_id
            print(f"  created tenant {ORG_SLUG} ({OWNER_EMAIL})")
        else:
            # psycopg hands back a UUID object; the SUT sets it as a text
            # setting for row-level security and will not cast it for you.
            org_id = str(row["id"])
            print(f"  tenant {ORG_SLUG} already exists")

        counts = ingest.sync_documents(org_id, SOURCE, loaded.as_items())
        print(f"  sync: {counts}")
        if counts["enqueued"] == 0 and counts["unchanged"]:
            print("  nothing re-embedded; content is unchanged. Use --reset to force it.")

        processed = ingest.run_pending()
        print(f"  ingest: {processed}")

        with connect(org_id) as conn:
            chunks = conn.execute(
                "select count(*) as n from chunks where org_id = %s", (org_id,)
            ).fetchone()["n"]
        print(f"  {chunks} chunks indexed, embedded by {'mock' if mock else settings.embed_model}")
    finally:
        # The pool's finalizer cannot join its threads at interpreter shutdown
        # on 3.14, so a short-lived process closes it itself. The system under
        # test learned this one first; see its seed.py.
        close_pool()

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mock",
        action="store_true",
        help="index with mock embeddings anyway; the result cannot be scored",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete the tenant first, so every document is re-embedded",
    )
    args = parser.parse_args()
    return load(allow_mock=args.mock, reset=args.reset)


if __name__ == "__main__":
    sys.exit(main())
