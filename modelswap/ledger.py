"""What this project has spent, and what it has left.

The per-run ceilings in `answers` and `judge` stop one command running away.
They do nothing about six sensible commands adding up to more than the project
was ever meant to cost, which is exactly how the first budget went: no single
run looked unreasonable.

So every run that spends records what it actually spent, and every run that is
about to spend checks its estimate against what is left rather than only against
its own ceiling.

The ledger starts from the moment it was added. It does not know about earlier
spending, and it says so rather than implying a total it cannot vouch for.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from modelswap.sut import repo_root

# What the whole project may spend from here on. A portfolio proof of concept,
# not a research budget.
PROJECT_BUDGET_USD = 2.00


@dataclass(frozen=True)
class Entry:
    kind: str
    variant: str
    items: int
    spent_usd: float
    at: str


def ledger_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / "cache" / "spend.json"


def entries(root: Path | None = None) -> list[Entry]:
    path = ledger_path(root)
    if not path.is_file():
        return []
    return [Entry(**record) for record in json.loads(path.read_text(encoding="utf-8"))]


def record(kind: str, variant: str, items: int, spent_usd: float, root: Path | None = None) -> None:
    """Append one run's actual spend. Called after the run, not before."""
    existing = entries(root)
    existing.append(
        Entry(
            kind=kind,
            variant=variant,
            items=items,
            spent_usd=round(spent_usd, 6),
            at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
    )
    path = ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(entry) for entry in existing], indent=2), encoding="utf-8")


def total_spent(root: Path | None = None) -> float:
    return sum(entry.spent_usd for entry in entries(root))


def remaining(root: Path | None = None, budget: float = PROJECT_BUDGET_USD) -> float:
    return budget - total_spent(root)


def headroom_for(
    estimate: float, root: Path | None = None, budget: float = PROJECT_BUDGET_USD
) -> str | None:
    """Why this run must not go ahead, or None if it fits inside the budget."""
    left = remaining(root, budget)
    if estimate > left:
        return (
            f"${estimate:.2f} does not fit in the ${left:.2f} left of the"
            f" ${budget:.2f} project budget (${total_spent(root):.2f} spent so far)."
            " Raise it deliberately with --budget."
        )
    return None


def summary(root: Path | None = None, budget: float = PROJECT_BUDGET_USD) -> str:
    return (
        f"spent ${total_spent(root):.2f} of ${budget:.2f}," f" ${remaining(root, budget):.2f} left"
    )
