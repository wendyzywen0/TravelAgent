"""Guardrails in Python. Owned by agent C."""
from __future__ import annotations

from typing import Any

from trip_agent import config
from trip_agent.models import TripResponse

TOLERANCE = 0.01


class GuardError(ValueError):
    pass


def check_input(text: str) -> str:
    """Strip, reject empty or > MAX_INPUT_CHARS. Returns cleaned text."""
    cleaned = text.strip()
    if not cleaned:
        raise GuardError("Input is empty.")
    if len(cleaned) > config.MAX_INPUT_CHARS:
        raise GuardError(
            f"Input is {len(cleaned)} characters, over the {config.MAX_INPUT_CHARS}-character limit."
        )
    return cleaned


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= TOLERANCE


def _matches(value: float, pool: set[float]) -> bool:
    return any(_close(value, v) for v in pool)


def cross_check(resp: TripResponse, tool_calls: list[dict[str, Any]]) -> None:
    """Raise GuardError if any dollar figure in resp is not traceable to a tool result."""
    if resp.status != "ok":
        return
    suggestion = resp.suggestion
    if suggestion is None:
        return

    hotel_nightly: set[float] = set()
    flight_pp: set[float] = set()
    totals: set[float] = set()

    for call in tool_calls:
        if call.get("error"):
            continue
        name = call.get("name")
        result = call.get("result")
        if result is None:
            continue
        if name == "find_hotels" and isinstance(result, list):
            for hotel in result:
                if isinstance(hotel, dict) and "nightly_usd" in hotel:
                    hotel_nightly.add(float(hotel["nightly_usd"]))
        elif name == "estimate_flights" and isinstance(result, dict):
            if "round_trip_per_person_usd" in result:
                flight_pp.add(float(result["round_trip_per_person_usd"]))
        elif name == "compute_budget" and isinstance(result, dict):
            if "total_usd" in result:
                totals.add(float(result["total_usd"]))

    for dest in suggestion.destinations:
        if dest.hotel is not None and not _matches(dest.hotel.nightly_usd, hotel_nightly):
            raise GuardError(
                f"{dest.name}: hotel nightly price {dest.hotel.nightly_usd} matches no find_hotels result."
            )
        if dest.flight_estimate_usd is not None and not _matches(dest.flight_estimate_usd, flight_pp):
            raise GuardError(
                f"{dest.name}: flight estimate {dest.flight_estimate_usd} matches no estimate_flights result."
            )
        if dest.estimated_total_usd is not None and not _matches(dest.estimated_total_usd, totals):
            raise GuardError(
                f"{dest.name}: estimated total {dest.estimated_total_usd} matches no compute_budget result."
            )

    if suggestion.budget is not None and not _matches(suggestion.budget.total_usd, totals):
        raise GuardError(
            f"Budget total {suggestion.budget.total_usd} matches no compute_budget result."
        )
