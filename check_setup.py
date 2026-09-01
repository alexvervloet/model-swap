#!/usr/bin/env python3
"""Preflight check: can this repo measure anything yet?

Verifies the system under test is present and importable, that its database is
reachable, and reports which model it currently answers on. Exits nonzero on
the first hard failure so CI can gate on it.

    python check_setup.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from modelswap.sut import SutNotFound, find_sut


def _ok(msg: str) -> None:
    print(f"  ok   {msg}")


def _fail(msg: str) -> None:
    print(f"  FAIL {msg}")


def _check_sut() -> Path | None:
    try:
        path = find_sut()
    except SutNotFound as exc:
        _fail(str(exc))
        return None
    _ok(f"system under test at {path}")
    return path


def _check_importable(sut: Path) -> Any:
    """Import the SUT's settings, adding its root to the path if needed."""
    if str(sut) not in sys.path:
        sys.path.insert(0, str(sut))
    try:
        from knowledge_desk.config import settings  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        _fail(f"knowledge_desk not importable: {exc}")
        _fail("install its requirements: pip install -r ../knowledge-desk/requirements.txt")
        return None
    _ok(f"knowledge_desk imports, answering on {settings.answer_model}")
    return settings


def _check_database(settings: Any) -> bool:
    try:
        import psycopg  # noqa: PLC0415
    except ImportError:
        _fail("psycopg not installed; it comes with the SUT's requirements")
        return False

    url = settings.database_url
    try:
        with psycopg.connect(url, connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute("select count(*) from documents")
            count = cur.fetchone()[0]
    except Exception as exc:  # noqa: BLE001
        _fail(f"database unreachable or unmigrated: {exc}")
        _fail(
            "from the sibling checkout: docker compose up -d db && python -m knowledge_desk.migrate"
        )
        return False
    _ok(f"database reachable, {count} document(s) indexed")
    if count == 0:
        print("       (seed it with `python -m knowledge_desk.seed` before measuring)")
    return True


def main() -> int:
    print("model-swap preflight")
    failures = 0

    sut = _check_sut()
    if sut is None:
        # Everything below needs it, so stop rather than print three more
        # failures that all say the same thing.
        print("\n1 check(s) failed")
        return 1

    settings = _check_importable(sut)
    if settings is None or not _check_database(settings):
        failures += 1

    print()
    if failures:
        print(f"{failures} check(s) failed")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
