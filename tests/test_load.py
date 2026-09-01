"""The loader's guards. The integration test needs the system under test's
database and is marked `sut` so it can be deselected without it.
"""

from __future__ import annotations

import pytest

from modelswap import load as loader
from modelswap.sut import ensure_importable


@pytest.fixture
def force_mock(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """`provider` is derived from the two keys, so forcing mock means clearing
    them rather than setting the property, which has no setter."""
    ensure_importable()
    from knowledge_desk.config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", None)
    monkeypatch.setattr(settings, "voyage_api_key", None)
    assert settings.provider == "mock"
    return settings


def test_refuses_to_index_with_mock_embeddings(
    force_mock, capsys: pytest.CaptureFixture[str]
) -> None:
    """The whole project is about not measuring nothing. An index of
    deterministic fake vectors is nothing, so the default path refuses it."""
    assert loader.load() == 1

    err = capsys.readouterr().err
    assert "refusing" in err
    assert "MOCK EMBEDDINGS" in err


def test_the_refusal_says_how_to_override(force_mock, capsys: pytest.CaptureFixture[str]) -> None:
    loader.load()
    err = capsys.readouterr().err
    assert "--mock" in err
    assert "VOYAGE_API_KEY" in err


@pytest.mark.sut
def test_loads_the_corpus_and_indexes_it(force_mock, capsys: pytest.CaptureFixture[str]) -> None:
    assert loader.load(allow_mock=True, reset=True) == 0

    out = capsys.readouterr().out
    assert "created tenant meridian" in out
    assert "'succeeded': 13" in out
    assert "chunks indexed" in out


@pytest.mark.sut
def test_a_second_run_re_embeds_nothing(force_mock, capsys: pytest.CaptureFixture[str]) -> None:
    """Reconciliation is on content hash, so switching embedding provider
    changes nothing on its own. The loader has to say so, or a scored run would
    quietly sit on vectors from the old provider."""
    loader.load(allow_mock=True, reset=True)
    capsys.readouterr()

    loader.load(allow_mock=True)

    out = capsys.readouterr().out
    assert "'enqueued': 0" in out
    assert "Use --reset to force it" in out
