"""Orchestration: extract -> gate -> bounded tool loop -> guards -> trace. Owned by the lead / agent L."""
from __future__ import annotations
from pathlib import Path
from trip_agent.models import TripResponse


def suggest_trip(text: str, client=None, trace_dir: Path | None = None, verbose: bool = False) -> TripResponse:
    raise NotImplementedError
