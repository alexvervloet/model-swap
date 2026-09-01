"""The locator has to work on a machine that has no checkout to find, so every
case here builds its own directory rather than depending on the real one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modelswap import sut


def _make_checkout(root: Path, name: str = "knowledge-desk") -> Path:
    """A directory that passes the marker check."""
    path = root / name
    (path / "knowledge_desk").mkdir(parents=True)
    (path / "knowledge_desk" / "config.py").write_text("settings = None\n")
    return path


def test_finds_the_sibling_checkout(tmp_path: Path) -> None:
    workspace = tmp_path / "AI"
    here = workspace / "model-swap"
    here.mkdir(parents=True)
    expected = _make_checkout(workspace)

    assert sut.find_sut(root=here) == expected


def test_env_var_wins_over_the_sibling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "AI"
    here = workspace / "model-swap"
    here.mkdir(parents=True)
    _make_checkout(workspace)
    elsewhere = _make_checkout(tmp_path / "somewhere-else", name="kd")

    monkeypatch.setenv(sut.ENV_VAR, str(elsewhere))

    assert sut.find_sut(root=here) == elsewhere


def test_a_directory_with_the_right_name_is_not_enough(tmp_path: Path) -> None:
    """An empty folder called knowledge-desk is the failure this guards: it
    resolves, then every import after it fails somewhere less obvious."""
    workspace = tmp_path / "AI"
    here = workspace / "model-swap"
    here.mkdir(parents=True)
    (workspace / "knowledge-desk").mkdir()

    with pytest.raises(sut.SutNotFound):
        sut.find_sut(root=here)


def test_the_error_names_every_path_it_tried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    here = tmp_path / "AI" / "model-swap"
    here.mkdir(parents=True)
    monkeypatch.setenv(sut.ENV_VAR, str(tmp_path / "nope"))

    with pytest.raises(sut.SutNotFound) as caught:
        sut.find_sut(root=here)

    message = str(caught.value)
    assert str(tmp_path / "nope") in message
    assert str(tmp_path / "AI" / "knowledge-desk") in message
    assert sut.ENV_VAR in message


def test_env_var_is_ignored_when_unset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(sut.ENV_VAR, raising=False)
    labels = [label for label, _ in sut.candidates(root=tmp_path)]
    assert labels == ["sibling checkout"]
