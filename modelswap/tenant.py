"""Open the Meridian tenant in-process.

Everything that measures needs the same thing: a TenantScope for the tenant the
corpus lives in, acting as its owner. This builds one straight from the database
rather than through login, because there is no session to speak of and no HTTP
in the measurement path.
"""

from __future__ import annotations

from typing import Any

from modelswap.load import ORG_SLUG, OWNER_EMAIL
from modelswap.sut import ensure_importable


class TenantMissing(RuntimeError):
    """The corpus tenant does not exist yet."""


def open_scope() -> Any:
    """A TenantScope for the corpus tenant, acting as its owner."""
    ensure_importable()
    from knowledge_desk.db import connect  # noqa: PLC0415
    from knowledge_desk.tenancy import AuthContext, TenantScope  # noqa: PLC0415

    with connect() as conn:
        row = conn.execute(
            "select o.id as org_id, u.id as user_id from orgs o"
            " join memberships m on m.org_id = o.id"
            " join users u on u.id = m.user_id"
            " where o.slug = %s and u.email = %s",
            (ORG_SLUG, OWNER_EMAIL),
        ).fetchone()

    if row is None:
        raise TenantMissing(
            f"tenant {ORG_SLUG!r} not found. Load the corpus first:" " python -m modelswap.load"
        )

    ctx = AuthContext(
        user_id=str(row["user_id"]),
        org_id=str(row["org_id"]),
        role="owner",
        email=OWNER_EMAIL,
    )
    return TenantScope(ctx)


def embed(text: str) -> list[float]:
    """One query embedding, from whichever embedder the settings resolve to.

    `embed_query`, not `embed_documents`. Voyage embeds a question and a passage
    with different input types, and using the passage side for a question is the
    kind of mistake that degrades retrieval without ever failing.
    """
    ensure_importable()
    from knowledge_desk.embeddings import get_embedder  # noqa: PLC0415

    vector: list[float] = get_embedder().embed_query(text)
    return vector
