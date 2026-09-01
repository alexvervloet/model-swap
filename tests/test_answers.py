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
    answers.write_cached(_answer(variant="claude-sonnet-5", text="sonnet"), tmp_path)
    answers.write_cached(_answer(variant="claude-haiku-4-5", text="haiku"), tmp_path)

    sonnet = answers.read_cached(
        "single-adult-fare-kilomre",
        "claude-sonnet-5",
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
    assert (sonnet.text, haiku.text) == ("sonnet", "haiku")  # type: ignore[union-attr]


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


def test_the_estimate_is_priced_at_the_dearest_model_in_play() -> None:
    """It quotes Sonnet rates whatever the variant, so the number shown before
    spending is never lower than what gets spent."""
    assert answers.estimate(0) == 0
    assert answers.estimate(120) > answers.estimate(60) > 0
    # A full pass over the question set is about a dollar, and the ceiling is
    # set so that one fits under it and a careless --samples 5 does not.
    assert 0.5 < answers.estimate(120) < answers.MAX_SPEND_USD
    assert answers.estimate(120 * 5) > answers.MAX_SPEND_USD


def test_opus_is_not_a_candidate() -> None:
    """Removed on purpose. One exploratory afternoon on Opus cost more than
    this project's entire budget, and the migration question worth asking is
    the one where somebody is trying to spend less."""
    assert "claude-opus-5" not in answers.VARIANTS
    assert answers.VARIANTS == ("claude-sonnet-5", "claude-haiku-4-5")


def test_a_failed_generation_is_not_a_cache_hit(tmp_path: Path) -> None:
    """97 of one run's 120 answers failed when the database went out from under
    it. Every one of those was written to the cache, and a rerun would have
    reported them as already done and scored an outage as the model's fault."""
    answers.write_cached(_answer(text="", error="Answer generation failed."), tmp_path)

    found = answers.read_cached(
        "single-adult-fare-kilomre",
        "claude-sonnet-5",
        0,
        "abc123def456",
        "How much is a ticket?",
        tmp_path,
    )
    assert found is None
    # Still on disk to be read.
    assert list(tmp_path.rglob("*.json"))


def test_an_unrecorded_index_is_refused(tmp_path: Path) -> None:
    from modelswap import tenant

    assert tenant.verify_index("abc", "org-1", tmp_path) is not None


def test_a_reloaded_tenant_invalidates_the_index(tmp_path: Path) -> None:
    """knowledge-desk mints a fresh org id on every tenant create, so a
    different id means something reindexed the corpus since this record was
    written. That is the failure a mock-embedding check cannot see."""
    from modelswap import tenant

    tenant.record_index(
        tenant.IndexState(
            org_id="org-1",
            corpus_version="abc",
            embed_model="voyage-3",
            provider="real",
            loaded_at="2026-09-01T00:00:00+00:00",
        ),
        tmp_path,
    )

    assert tenant.verify_index("abc", "org-1", tmp_path) is None
    assert "reloaded" in (tenant.verify_index("abc", "org-2", tmp_path) or "")


def test_a_mock_built_index_is_refused_even_with_a_real_key(tmp_path: Path) -> None:
    from modelswap import tenant

    tenant.record_index(
        tenant.IndexState(
            org_id="org-1",
            corpus_version="abc",
            embed_model="mock",
            provider="mock",
            loaded_at="2026-09-01T00:00:00+00:00",
        ),
        tmp_path,
    )

    assert "mock" in (tenant.verify_index("abc", "org-1", tmp_path) or "")


def test_edited_documents_invalidate_the_index(tmp_path: Path) -> None:
    from modelswap import tenant

    tenant.record_index(
        tenant.IndexState(
            org_id="org-1",
            corpus_version="abc",
            embed_model="voyage-3",
            provider="real",
            loaded_at="2026-09-01T00:00:00+00:00",
        ),
        tmp_path,
    )

    assert "documents on disk" in (tenant.verify_index("xyz", "org-1", tmp_path) or "")


def test_the_ceiling_is_low_enough_to_matter() -> None:
    """The credit balance went from fine to empty inside one afternoon, so the
    ceiling has to sit below the runs that would do that, not above them."""
    one_pass = answers.estimate(120)
    five_samples = answers.estimate(120 * 5)

    assert one_pass < answers.MAX_SPEND_USD, "a single pass has to fit"
    assert five_samples > answers.MAX_SPEND_USD, "a careless --samples 5 must not"
    assert answers.MAX_SPEND_USD <= 2.0, "this is a portfolio project"


def test_the_judge_has_its_own_ceiling() -> None:
    """Judging is the cost everybody forgets: it is a second model call per
    answer, and it scales with samples the same way generation does."""
    from modelswap import judge

    assert judge.estimate(240) < judge.MAX_SPEND_USD
    assert judge.MAX_SPEND_USD <= 2.0
