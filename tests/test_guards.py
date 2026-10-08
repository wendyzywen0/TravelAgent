from __future__ import annotations

import pytest

from trip_agent.guards import GuardError, check_input, cross_check
from trip_agent.models import (
    BudgetSummary,
    DestinationPick,
    HotelPick,
    TripResponse,
    TripSuggestion,
)

COMPUTE_BUDGET_CALL = {
    "kind": "tool_call",
    "name": "compute_budget",
    "args": {},
    "result": {
        "total_usd": 1800.0,
        "breakdown": {"flights": 800.0, "hotel": 1000.0},
        "fits": True,
        "over_by_usd": None,
        "includes_flights": True,
    },
    "duration_s": 0.01,
}

FIND_HOTELS_CALL = {
    "kind": "tool_call",
    "name": "find_hotels",
    "args": {},
    "result": [{"name": "Hotel A", "destination": "Lisbon", "nightly_usd": 120.0, "tags": []}],
    "duration_s": 0.01,
}

ESTIMATE_FLIGHTS_CALL = {
    "kind": "tool_call",
    "name": "estimate_flights",
    "args": {},
    "result": {"origin": "JFK", "destination": "Lisbon", "round_trip_per_person_usd": 400.0, "hours": 7.0},
    "duration_s": 0.01,
}


def _suggestion(estimated_total_usd: float | None, budget_total_usd: float | None = 1800.0) -> TripSuggestion:
    dest = DestinationPick(
        name="Lisbon",
        country="Portugal",
        why="warm and cheap in Feb",
        hotel=HotelPick(name="Hotel A", nightly_usd=120.0, tags=[]),
        flight_estimate_usd=400.0,
        estimated_total_usd=estimated_total_usd,
    )
    budget = (
        BudgetSummary(total_usd=budget_total_usd, user_budget_usd=2000.0, fits=True, breakdown={"flights": 800.0, "hotel": 1000.0})
        if budget_total_usd is not None
        else None
    )
    return TripSuggestion(destinations=[dest], reasoning="grounded in tool results", budget=budget, caveats=[])


# ---- check_input (AC11) ----


def test_check_input_rejects_empty():
    with pytest.raises(GuardError):
        check_input("")
    with pytest.raises(GuardError):
        check_input("   ")


def test_check_input_rejects_over_limit():
    with pytest.raises(GuardError):
        check_input("x" * 2001)


def test_check_input_strips_and_passes_through():
    assert check_input("  beach week  ") == "beach week"
    assert check_input("x" * 2000) == "x" * 2000


# ---- cross_check (AC12) ----


def test_cross_check_raises_on_mismatched_total():
    resp = TripResponse(status="ok", suggestion=_suggestion(estimated_total_usd=9999.0))
    tool_calls = [COMPUTE_BUDGET_CALL, FIND_HOTELS_CALL, ESTIMATE_FLIGHTS_CALL]
    with pytest.raises(GuardError):
        cross_check(resp, tool_calls)


def test_cross_check_passes_when_figures_match():
    resp = TripResponse(status="ok", suggestion=_suggestion(estimated_total_usd=1800.0))
    tool_calls = [COMPUTE_BUDGET_CALL, FIND_HOTELS_CALL, ESTIMATE_FLIGHTS_CALL]
    cross_check(resp, tool_calls)  # should not raise


def test_cross_check_passes_for_needs_info_with_no_tool_calls():
    resp = TripResponse(status="needs_info", questions=["What's your budget?"])
    cross_check(resp, [])  # should not raise


def test_cross_check_raises_on_mismatched_hotel_price():
    resp = TripResponse(status="ok", suggestion=_suggestion(estimated_total_usd=1800.0))
    # hotel tool call missing, so the 120.0 nightly price can't be verified
    tool_calls = [COMPUTE_BUDGET_CALL, ESTIMATE_FLIGHTS_CALL]
    with pytest.raises(GuardError):
        cross_check(resp, tool_calls)
