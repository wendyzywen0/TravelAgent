"""One JSON trace per request. Owned by agent C."""
from __future__ import annotations

import json
import logging
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from trip_agent.config import PROJECT_ROOT

from pydantic import BaseModel

logger = logging.getLogger("trip_agent")

# Kinds that also get a one-line INFO summary (everything gets a DEBUG line).
_SUMMARY_KINDS = {"gate", "final", "error"}


def _json_safe(value: Any) -> Any:
    """Make event data JSON-serializable: pydantic models -> dict, Path/date -> str."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "isoformat"):  # date / datetime
        return value.isoformat()
    return value


class Tracer:
    def __init__(self, raw_input: str, trace_dir: Path | None = None, verbose: bool = False) -> None:
        self.request_id: str = secrets.token_hex(4)  # 8 hex chars
        self.trace_dir: Path = trace_dir if trace_dir is not None else PROJECT_ROOT / "traces"
        self.verbose: bool = verbose
        self.raw_input: str = raw_input
        self.started_at: str = datetime.now(timezone.utc).isoformat()
        self._clock0: float = time.monotonic()
        self.events: list[dict[str, Any]] = []
        self.usage: list[dict[str, Any]] = []
        self.event("input", raw_input=raw_input)

    def event(self, kind: str, **data: Any) -> None:
        """kinds: input, extraction, gate, tool_call, model_call, final, error"""
        safe_data = {k: _json_safe(v) for k, v in data.items()}
        entry: dict[str, Any] = {
            "kind": kind,
            "t": round(time.monotonic() - self._clock0, 3),
            **safe_data,
        }
        self.events.append(entry)

        logger.debug("%s %s", self.request_id, entry)
        if kind in _SUMMARY_KINDS:
            logger.info("%s [%s] %s", self.request_id, kind, entry)
        if self.verbose:
            print(json.dumps(entry), file=sys.stderr)

    def add_usage(self, model: str, input_tokens: int, output_tokens: int, duration_s: float, purpose: str) -> None:
        record = {
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "duration_s": duration_s,
            "purpose": purpose,
        }
        self.usage.append(record)
        self.event("model_call", **record)

    def tool_calls(self) -> list[dict[str, Any]]:
        """All tool_call events so far (name, args, result, duration_s)."""
        return [e for e in self.events if e.get("kind") == "tool_call"]

    def write(self) -> Path:
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        path = self.trace_dir / f"{stamp}_{self.request_id}.json"

        totals = {
            "input_tokens": sum(u["input_tokens"] for u in self.usage),
            "output_tokens": sum(u["output_tokens"] for u in self.usage),
            "model_calls": len(self.usage),
            "tool_calls": len(self.tool_calls()),
        }
        payload = {
            "request_id": self.request_id,
            "input": self.raw_input,
            "started_at": self.started_at,
            "events": self.events,
            "usage": self.usage,
            "totals": totals,
        }
        path.write_text(json.dumps(payload, indent=2))
        return path
