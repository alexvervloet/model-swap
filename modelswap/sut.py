"""Locate the system under test.

model-swap measures knowledge-desk, which lives in its own repository. This is
the only module that knows how to find it, so a checkout kept somewhere unusual
is one environment variable rather than a search across the codebase.

Deliberately dependency-free. The tests for it must run on a machine that has
no knowledge-desk checkout at all, which is also what CI looks like in the lint
job.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "KNOWLEDGE_DESK_PATH"
SIBLING_NAME = "knowledge-desk"

# The file that proves a directory is the checkout rather than a same-named
# empty folder. Any file unique to the repo would do; config.py is one the
# runner will import anyway.
MARKER = Path("knowledge_desk") / "config.py"


class SutNotFound(RuntimeError):
    """The knowledge-desk checkout could not be located."""


def repo_root() -> Path:
    """This repository's root, resolved from this file rather than the cwd."""
    return Path(__file__).resolve().parent.parent


def candidates(root: Path | None = None) -> list[tuple[str, Path]]:
    """Every place worth looking, labeled, in the order they are tried."""
    root = root or repo_root()
    found: list[tuple[str, Path]] = []
    override = os.environ.get(ENV_VAR)
    if override:
        found.append((f"${ENV_VAR}", Path(override).expanduser().resolve()))
    found.append(("sibling checkout", root.parent / SIBLING_NAME))
    return found


def looks_like_sut(path: Path) -> bool:
    """Is this directory actually the checkout, and not just named like it?"""
    return (path / MARKER).is_file()


def find_sut(root: Path | None = None) -> Path:
    """Return the knowledge-desk checkout, or say exactly where it was not.

    An error that names the paths it tried is the difference between a
    one-second fix and a confused half hour, and this is the first thing a
    reader of this repo will run.
    """
    tried: list[str] = []
    for label, path in candidates(root):
        if looks_like_sut(path):
            return path
        tried.append(f"    {label}: {path}")
    raise SutNotFound(
        "knowledge-desk checkout not found. Looked in:\n"
        + "\n".join(tried)
        + f"\n  Clone it beside this repo, or set {ENV_VAR} to point at it."
    )
