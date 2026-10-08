"""Guardrails in Python. Owned by agent C."""
from __future__ import annotations
from typing import Any
from trip_agent.models import TripResponse


class GuardError(ValueError):
    pass


def check_input(text: str) -> str:
    """Strip, reject empty or > MAX_INPUT_CHARS. Returns cleaned text."""
    raise NotImplementedError


def cross_check(resp: TripResponse, tool_calls: list[dict[str, Any]]) -> None:
    """Raise GuardError if any dollar figure in resp is not traceable to a tool result."""
    raise NotImplementedError
