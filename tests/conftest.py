"""Test-wide fixtures.

The locator reads process environment, so every test that does not set
`KNOWLEDGE_DESK_PATH` itself must start without one. Otherwise a machine that
happens to export it (CI does) silently answers the question under test, and
the suite passes for a reason that has nothing to do with the code.
"""

from __future__ import annotations

import pytest

from modelswap import sut


@pytest.fixture(autouse=True)
def _no_ambient_sut_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear the override so each test declares its own environment."""
    monkeypatch.delenv(sut.ENV_VAR, raising=False)
