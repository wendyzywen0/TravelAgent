"""Project cost ledger. Owned by agent C."""
from __future__ import annotations
from pathlib import Path

LEDGER_PATH = Path("cost_ledger.json")


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    raise NotImplementedError


def record(run_label: str, cost_usd: float, input_tokens: int, output_tokens: int, path: Path = LEDGER_PATH) -> float:
    """Append and return the new cumulative total."""
    raise NotImplementedError


def check_cap(path: Path = LEDGER_PATH) -> None:
    """Raise RuntimeError if cumulative spend >= PROJECT_COST_CAP_USD."""
    raise NotImplementedError
