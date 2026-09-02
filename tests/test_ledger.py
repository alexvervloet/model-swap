"""The per-run ceilings stop one command running away. They do nothing about six
sensible commands adding up, which is exactly how the first budget went."""

from __future__ import annotations

from pathlib import Path

from modelswap import ledger


def test_an_empty_ledger_has_the_whole_budget(tmp_path: Path) -> None:
    assert ledger.total_spent(tmp_path) == 0.0
    assert ledger.remaining(tmp_path) == ledger.PROJECT_BUDGET_USD


def test_spending_accumulates_across_runs(tmp_path: Path) -> None:
    ledger.record("answers", "claude-sonnet-5", 120, 0.96, tmp_path)
    ledger.record("judge", "claude-sonnet-5", 120, 0.24, tmp_path)

    assert ledger.total_spent(tmp_path) == 1.20
    assert ledger.remaining(tmp_path) == round(ledger.PROJECT_BUDGET_USD - 1.20, 6)


def test_a_run_that_fits_is_allowed(tmp_path: Path) -> None:
    ledger.record("answers", "claude-sonnet-5", 120, 0.96, tmp_path)
    assert ledger.headroom_for(0.50, tmp_path) is None


def test_a_run_that_does_not_fit_is_refused_with_the_numbers(tmp_path: Path) -> None:
    """No single run here looks unreasonable. That is the point: the ceiling
    that matters is the one on the total."""
    ledger.record("answers", "claude-sonnet-5", 120, 0.96, tmp_path)
    ledger.record("judge", "claude-sonnet-5", 120, 0.24, tmp_path)
    ledger.record("judge", "claude-haiku-4-5", 120, 0.24, tmp_path)

    refusal = ledger.headroom_for(0.90, tmp_path)

    assert refusal is not None
    assert "1.44" in refusal
    assert "$0.56 left" in refusal


def test_the_budget_can_be_raised_deliberately(tmp_path: Path) -> None:
    ledger.record("answers", "claude-sonnet-5", 120, 1.90, tmp_path)

    assert ledger.headroom_for(0.50, tmp_path) is not None
    assert ledger.headroom_for(0.50, tmp_path, budget=5.0) is None


def test_the_summary_reads_as_a_sentence(tmp_path: Path) -> None:
    ledger.record("answers", "claude-sonnet-5", 120, 0.96, tmp_path)
    assert ledger.summary(tmp_path) == "spent $0.96 of $2.00, $1.04 left"


def test_the_budget_is_the_declared_one() -> None:
    assert ledger.PROJECT_BUDGET_USD == 2.00
