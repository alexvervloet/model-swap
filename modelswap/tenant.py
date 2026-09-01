"""Open the Meridian tenant in-process.

Everything that measures needs the same thing: a TenantScope for the tenant the
corpus lives in, acting as its owner. This builds one straight from the database
rather than through login, because there is no session to speak of and no HTTP
in the measurement path.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from modelswap.sut import ensure_importable, repo_root

# The tenant the corpus lives in. Here rather than in `load`, because the loader
# needs the index record and the index record needs the tenant's identity: the
# two modules would otherwise import each other.
ORG_SLUG = "meridian"
ORG_NAME = "Meridian Ferries"
OWNER_EMAIL = "owner@meridian.test"

# S105: a throwaway login for a local demo tenant, matching the seed data in the
# system under test. Nothing here reaches a deployment.
OWNER_PASSWORD = "demo-password-123"  # noqa: S105


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


@dataclass(frozen=True)
class IndexState:
    """What the corpus was last loaded as, recorded at load and checked at use."""

    org_id: str
    corpus_version: str
    embed_model: str
    provider: str
    loaded_at: str


def state_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / "cache" / "index.json"


def record_index(state: IndexState, root: Path | None = None) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2, sort_keys=True), encoding="utf-8")


def read_index(root: Path | None = None) -> IndexState | None:
    path = state_path(root)
    if not path.is_file():
        return None
    return IndexState(**json.loads(path.read_text(encoding="utf-8")))


def verify_index(corpus_version: str, org_id: str, root: Path | None = None) -> str | None:
    """Return why this index must not be measured, or None if it is sound.

    The org id is the load's fingerprint: knowledge-desk mints a fresh one every
    time a tenant is created, so anything that reset and reloaded the corpus
    changed it. That catches the failure a mock-embedding check cannot, which is
    a reindex by something that was not this project's loader.

    The loader refuses to build a mock index. This is the other half: a run
    refusing to read one. A guard on the write path is not a guard on the read
    path, which is LESSONS 9.
    """
    state = read_index(root)
    if state is None:
        return "no index record. Load the corpus: python -m modelswap.load"
    if state.provider != "real":
        return f"index was built with the {state.provider} provider and cannot be scored"
    if state.corpus_version != corpus_version:
        return (
            f"index was built from corpus {state.corpus_version[:12]},"
            f" the documents on disk are {corpus_version[:12]}"
        )
    if state.org_id != org_id:
        return (
            "the tenant has been reloaded since this index was recorded"
            f" ({state.org_id[:8]} then, {org_id[:8]} now)"
        )
    return None
