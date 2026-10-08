"""One JSON trace per request. Owned by agent C."""
from __future__ import annotations
from pathlib import Path
from typing import Any


class Tracer:
    def __init__(self, raw_input: str, trace_dir: Path | None = None, verbose: bool = False) -> None:
        self.request_id: str = ""
        raise NotImplementedError

    def event(self, kind: str, **data: Any) -> None:
        """kinds: input, extraction, gate, tool_call, model_call, final, error"""
        raise NotImplementedError

    def add_usage(self, model: str, input_tokens: int, output_tokens: int, duration_s: float, purpose: str) -> None:
        raise NotImplementedError

    def tool_calls(self) -> list[dict[str, Any]]:
        """All tool_call events so far (name, args, result, duration_s)."""
        raise NotImplementedError

    def write(self) -> Path:
        raise NotImplementedError
