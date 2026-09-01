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

# The server knowledge-desk's docker-compose brings up. Only the database name
# differs; the credentials and port are its own.
_HOST = "localhost:5436"
DATABASE_URL = f"postgresql://kd:kd@{_HOST}/{DB_NAME}"
APP_DATABASE_URL = f"postgresql://kd_app:kd_app@{_HOST}/{DB_NAME}"

# The maintenance database used to issue CREATE DATABASE, which cannot run
# inside a transaction or against the database being created.
_MAINTENANCE_URL = f"postgresql://kd:kd@{_HOST}/postgres"


def configure() -> None:
    """Point the system under test at our database. Idempotent.

    Respects an explicit override so a developer can aim this somewhere else,
    but never inherits knowledge-desk's default by accident.
    """
    os.environ.setdefault("DATABASE_URL", DATABASE_URL)
    os.environ.setdefault("APP_DATABASE_URL", APP_DATABASE_URL)


def exists() -> bool:
    import psycopg  # noqa: PLC0415

    with psycopg.connect(_MAINTENANCE_URL, connect_timeout=5) as conn:
        found = conn.execute("select 1 from pg_database where datname = %s", (DB_NAME,)).fetchone()
    return found is not None


def create() -> bool:
    """Create the database if it is missing. Returns whether it created it."""
    import psycopg  # noqa: PLC0415

    if exists():
        return False
    # autocommit: CREATE DATABASE is refused inside a transaction block.
    with psycopg.connect(_MAINTENANCE_URL, connect_timeout=5, autocommit=True) as conn:
        conn.execute(f'create database "{DB_NAME}"')
    return True
