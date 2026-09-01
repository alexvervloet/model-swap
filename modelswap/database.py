"""A database of our own.

model-swap drives knowledge-desk in-process, which means it uses knowledge-desk's
schema. It does not follow that it should use knowledge-desk's *database*, and
the first long run proved it: knowledge-desk's test suite truncates every table
as a fixture, so running those tests deleted the corpus tenant while a paid
generation was 23 answers in. The remaining 97 answers failed on a foreign key
pointing at an org that no longer existed.

So this module points the system under test at `model_swap` on the same server
before its settings are ever read. Same Postgres, same schema, same migrations,
different database. The two projects stop being able to destroy each other.

**Import order matters.** knowledge-desk builds its `settings` object at module
import, reading the environment once. `configure()` therefore has to run before
anything imports `knowledge_desk.config`, which is why `modelswap.sut`'s
`ensure_importable` calls it rather than leaving it to each caller to remember.
"""

from __future__ import annotations

import os

DB_NAME = "model_swap"

# Tests reset tenants and reload with mock embeddings, so they cannot share the
# database a measurement run reads from. The first attempt at isolation fixed
# knowledge-desk's tests and left this one, which is the same bug one level in.
TEST_DB_NAME = "model_swap_test"

# The server knowledge-desk's docker-compose brings up. Only the database name
# differs; the credentials and port are its own.
_HOST = "localhost:5436"


def urls(name: str) -> tuple[str, str]:
    """The owner and least-privilege URLs for one database on this server."""
    return (
        f"postgresql://kd:kd@{_HOST}/{name}",
        f"postgresql://kd_app:kd_app@{_HOST}/{name}",
    )


DATABASE_URL, APP_DATABASE_URL = urls(DB_NAME)

# The maintenance database used to issue CREATE DATABASE, which cannot run
# inside a transaction or against the database being created.
_MAINTENANCE_URL = f"postgresql://kd:kd@{_HOST}/postgres"


def configure(name: str = DB_NAME) -> None:
    """Point the system under test at one of our databases. Idempotent.

    Respects an explicit override so a developer can aim this somewhere else,
    but never inherits knowledge-desk's default by accident. Must run before
    anything imports `knowledge_desk.config`, which reads the environment once.
    """
    owner, app = urls(name)
    os.environ.setdefault("DATABASE_URL", owner)
    os.environ.setdefault("APP_DATABASE_URL", app)


def configured_name() -> str:
    """The database the environment currently points at.

    Anything that creates or migrates asks this rather than assuming the
    default, or a test run configured for `model_swap_test` migrates
    `model_swap` and then connects to a database nobody created.
    """
    return os.environ.get("DATABASE_URL", DATABASE_URL).rsplit("/", 1)[-1]


def exists(name: str | None = None) -> bool:
    import psycopg  # noqa: PLC0415

    name = name or configured_name()
    with psycopg.connect(_MAINTENANCE_URL, connect_timeout=5) as conn:
        found = conn.execute("select 1 from pg_database where datname = %s", (name,)).fetchone()
    return found is not None


def create(name: str | None = None) -> bool:
    """Create the database if it is missing. Returns whether it created it."""
    import psycopg  # noqa: PLC0415

    name = name or configured_name()
    if exists(name):
        return False
    # autocommit: CREATE DATABASE is refused inside a transaction block.
    with psycopg.connect(_MAINTENANCE_URL, connect_timeout=5, autocommit=True) as conn:
        conn.execute(f'create database "{name}"')
    return True
