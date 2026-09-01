"""The cache is the expensive artefact, so its miss conditions matter more than
its hit conditions."""

from __future__ import annotations

from pathlib import Path

from modelswap import answers


def _answer(**overrides: object) -> answers.Answer:
    fields: dict[str, object] = {
        "qid": "single-adult-fare-kilomre",
        "variant": "claude-sonnet-5",
        "sample": 0,
        "question": "How much is a ticket?",
        "text": "£9.40 [1]",
        "sources": ["03-fares-and-tickets"],
        "input_tokens": 3000,
        "output_tokens": 40,
        "cost_usd": 0.0064,
        "seconds": 2.5,
        "corpus_version": "abc123def456",
    }
    fields.update(overrides)
    return answers.Answer(**fields)  # type: ignore[arg-type]


def test_a_cached_answer_round_trips(tmp_path: Path) -> None:
    original = _answer()
    answers.write_cached(original, tmp_path)

    found = answers.read_cached(
        original.qid,
        original.variant,
        original.sample,
        original.corpus_version,
        original.question,
        tmp_path,
    )
    assert found == original


def test_a_changed_question_is_a_miss(tmp_path: Path) -> None:
    """The id stays the same when a question is reworded, and the answer on
    disk is an answer to the old one. Reusing it would compare two models on
    two different questions."""
    original = _answer()
    answers.write_cached(original, tmp_path)

    found = answers.read_cached(
        original.qid,
        original.variant,
        original.sample,
        original.corpus_version,
        "How much is a ticket, roughly?",
        tmp_path,
    )
    assert found is None


def test_a_different_corpus_version_is_a_miss(tmp_path: Path) -> None:
    original = _answer()
    answers.write_cached(original, tmp_path)

    found = answers.read_cached(
        original.qid,
        original.variant,
        original.sample,
        "999999999999",
        original.question,
        tmp_path,
    )
    assert found is None


def test_variants_do_not_share_a_cache_entry(tmp_path: Path) -> None:
    answers.write_cached(_answer(variant="claude-opus-5", text="opus"), tmp_path)
    answers.write_cached(_answer(variant="claude-haiku-4-5", text="haiku"), tmp_path)

    opus = answers.read_cached(
        "single-adult-fare-kilomre",
        "claude-opus-5",
        0,
        "abc123def456",
        "How much is a ticket?",
        tmp_path,
    )
    haiku = answers.read_cached(
        "single-adult-fare-kilomre",
        "claude-haiku-4-5",
        0,
        "abc123def456",
        "How much is a ticket?",
        tmp_path,
    )
    assert (opus.text, haiku.text) == ("opus", "haiku")  # type: ignore[union-attr]


def test_samples_do_not_share_a_cache_entry(tmp_path: Path) -> None:
    """Samples are the whole point: the same question twice is how variance
    gets measured."""
    answers.write_cached(_answer(sample=0, text="first"), tmp_path)
    answers.write_cached(_answer(sample=1, text="second"), tmp_path)

    first = answers.read_cached(
        "single-adult-fare-kilomre",
        "claude-sonnet-5",
        0,
        "abc123def456",
        "How much is a ticket?",
        tmp_path,
    )
    second = answers.read_cached(
        "single-adult-fare-kilomre",
        "claude-sonnet-5",
        1,
        "abc123def456",
        "How much is a ticket?",
        tmp_path,
    )
    assert (first.text, second.text) == ("first", "second")  # type: ignore[union-attr]


def test_the_estimate_is_an_upper_bound_priced_at_opus() -> None:
    """It quotes Opus rates whatever the variant, so the number shown before
    spending is never lower than what gets spent."""
    assert answers.estimate(0) == 0
    assert answers.estimate(120) > answers.estimate(60) > 0
    # 120 answers on this corpus should be single-digit dollars, not tens.
    assert 1.0 < answers.estimate(120) < 10.0
