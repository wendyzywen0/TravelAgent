"""Project cost ledger. Owned by agent C."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from trip_agent import config

LEDGER_PATH = Path("cost_ledger.json")


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate, out_rate = config.PRICE_PER_MTOK.get(model, config.PRICE_PER_MTOK["claude-opus-4-8"])
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000


def record(run_label: str, cost_usd: float, input_tokens: int, output_tokens: int, path: Path = LEDGER_PATH) -> float:
    """Append and return the new cumulative total."""
    if path.exists():
        data = json.loads(path.read_text())
    else:
        data = {"runs": [], "total_usd": 0.0}

    data["runs"].append(
        {
            "run_label": run_label,
            "cost_usd": cost_usd,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )
    data["total_usd"] = data.get("total_usd", 0.0) + cost_usd

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    return data["total_usd"]


def check_cap(path: Path = LEDGER_PATH) -> None:
    """Raise RuntimeError if cumulative spend >= PROJECT_COST_CAP_USD."""
    if not path.exists():
        return
    data = json.loads(path.read_text())
    total = data.get("total_usd", 0.0)
    if total >= config.PROJECT_COST_CAP_USD:
        raise RuntimeError(
            f"Project cost ledger is at ${total:.2f}, at or over the ${config.PROJECT_COST_CAP_USD:.2f} cap."
        )
