from __future__ import annotations

import copy
from typing import Any

import pytest

from trip_agent.guards import GuardError, check_input, cross_check
from trip_agent.models import (
    BudgetSummary,
    DestinationPick,
    HotelPick,
    TripResponse,
    TripSuggestion,
)


def _call(name: str, args: dict[str, Any], result: Any, error: str | None = None) -> dict[str, Any]:
    return {"kind": "tool_call", "name": name, "args": args, "result": result, "duration_s": 0.01, "error": error}


# Realistic trace: Lisbon hotel 120/night x 7 nights, flights 400pp x 2 travelers.
FIND_HOTELS_CALL = _call(
    "find_hotels",
    {"destination": "Lisbon", "style": None, "nightly_cap_usd": None, "must_haves": []},
    [{"name": "Hotel A", "destination": "Lisbon", "nightly_usd": 120.0, "tags": []}],
)

ESTIMATE_FLIGHTS_CALL = _call(
    "estimate_flights",
    {"origin": "JFK", "destination": "Lisbon", "month": "February"},
    {"origin": "JFK", "destination": "Lisbon", "round_trip_per_person_usd": 400.0, "hours": 7.0},
)

COMPUTE_BUDGET_CALL = _call(
    "compute_budget",
    {"flight_per_person_usd": 400.0, "travelers": 2, "nightly_usd": 120.0, "nights": 7,
     "user_budget_usd": 2000.0, "includes_flights": True},
    {"total_usd": 1640.0, "breakdown": {"flights": 800.0, "hotel": 840.0}, "fits": True,
     "over_by_usd": 0.0, "includes_flights": True},
)

TOOL_CALLS = [FIND_HOTELS_CALL, ESTIMATE_FLIGHTS_CALL, COMPUTE_BUDGET_CALL]


def _suggestion(estimated_total_usd: float | None, budget_total_usd: float | None = 1640.0) -> TripSuggestion:
    dest = DestinationPick(
        name="Lisbon",
        country="Portugal",
        why="warm and cheap in Feb",
        hotel=HotelPick(name="Hotel A", nightly_usd=120.0, tags=[]),
        flight_estimate_usd=400.0,
        estimated_total_usd=estimated_total_usd,
    )
    budget = (
        BudgetSummary(total_usd=budget_total_usd, user_budget_usd=2000.0, fits=True, over_by_usd=0.0,
                      breakdown={"flights": 800.0, "hotel": 840.0}, includes_flights=True)
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
    tool_calls = TOOL_CALLS
    with pytest.raises(GuardError):
        cross_check(resp, tool_calls)


def test_cross_check_passes_when_figures_match():
    resp = TripResponse(status="ok", suggestion=_suggestion(estimated_total_usd=1640.0))
    tool_calls = TOOL_CALLS
    cross_check(resp, tool_calls)  # should not raise


def test_cross_check_passes_for_needs_info_with_no_tool_calls():
    resp = TripResponse(status="needs_info", questions=["What's your budget?"])
    cross_check(resp, [])  # should not raise


def test_cross_check_raises_on_mismatched_hotel_price():
    resp = TripResponse(status="ok", suggestion=_suggestion(estimated_total_usd=1640.0))
    # hotel tool call missing, so the 120.0 nightly price can't be verified
    tool_calls = [COMPUTE_BUDGET_CALL, ESTIMATE_FLIGHTS_CALL]
    with pytest.raises(GuardError):
        cross_check(resp, tool_calls)


def test_cross_check_passes_for_fully_consistent_realistic_trace():
    # Includes noise a real trace has: a search call, a failed flight lookup, a second destination.
    tool_calls = [
        _call("search_destinations", {"vibe": ["beach"], "season": "February", "region": None, "exclusions": []},
              [{"name": "Lisbon", "country": "Portugal", "region": "europe", "price_level": 2,
                "tags": ["city"], "typical_nightly_usd": 130.0}]),
        _call("estimate_flights", {"origin": "JFK", "destination": "Atlantis", "month": "February"}, None,
              error="no fare data for JFK→Atlantis"),
        _call("find_hotels", {"destination": "Cancun", "style": None, "nightly_cap_usd": None, "must_haves": []},
              [{"name": "Beach Inn", "destination": "Cancun", "nightly_usd": 95.0, "tags": ["beachfront"]}]),
        FIND_HOTELS_CALL,
        ESTIMATE_FLIGHTS_CALL,
        COMPUTE_BUDGET_CALL,
    ]
    resp = TripResponse(status="ok", suggestion=_suggestion(estimated_total_usd=1640.0))
    cross_check(resp, tool_calls)  # should not raise


def test_cross_check_accepts_alias_resolved_hotel_destination():
    hotels = copy.deepcopy(FIND_HOTELS_CALL)
    hotels["args"]["destination"] = "Lisboa, Portugal"  # tool resolved the alias to "Lisbon"
    resp = TripResponse(status="ok", suggestion=_suggestion(estimated_total_usd=1640.0))
    cross_check(resp, [hotels, ESTIMATE_FLIGHTS_CALL, COMPUTE_BUDGET_CALL])  # should not raise


# ---- (1) laundering through compute_budget ----


def test_cross_check_rejects_invented_nightly_passed_to_compute_budget():
    laundered = _call(
        "compute_budget",
        {"flight_per_person_usd": 400.0, "travelers": 2, "nightly_usd": 50.0, "nights": 7,
         "user_budget_usd": 2000.0, "includes_flights": True},
        {"total_usd": 1150.0, "breakdown": {"flights": 800.0, "hotel": 350.0}, "fits": True,
         "over_by_usd": 0.0, "includes_flights": True},
    )
    sug = _suggestion(estimated_total_usd=1640.0, budget_total_usd=None)
    sug.budget = BudgetSummary(total_usd=1150.0, user_budget_usd=2000.0, fits=True, over_by_usd=0.0,
                               breakdown={"flights": 800.0, "hotel": 350.0}, includes_flights=True)
    resp = TripResponse(status="ok", suggestion=sug)
    with pytest.raises(GuardError, match="1150"):
        cross_check(resp, [*TOOL_CALLS, laundered])


def test_cross_check_rejects_invented_flight_passed_to_compute_budget():
    laundered = copy.deepcopy(COMPUTE_BUDGET_CALL)
    laundered["args"]["flight_per_person_usd"] = 100.0  # no estimate_flights returned 100
    laundered["result"] = {"total_usd": 1040.0, "breakdown": {"flights": 200.0, "hotel": 840.0}, "fits": True,
                           "over_by_usd": 0.0, "includes_flights": True}
    resp = TripResponse(status="ok", suggestion=_suggestion(estimated_total_usd=1040.0, budget_total_usd=None))
    resp.suggestion.destinations[0].flight_estimate_usd = None  # type: ignore[union-attr]
    with pytest.raises(GuardError, match="1040"):
        cross_check(resp, [FIND_HOTELS_CALL, ESTIMATE_FLIGHTS_CALL, laundered])


# ---- (2) full budget summary must match one compute_budget result ----


def test_cross_check_rejects_breakdown_mismatch():
    sug = _suggestion(estimated_total_usd=1640.0)
    assert sug.budget is not None
    sug.budget.breakdown = {"flights": 640.0, "hotel": 1000.0}  # same total, wrong split
    with pytest.raises(GuardError, match="breakdown"):
        cross_check(TripResponse(status="ok", suggestion=sug), TOOL_CALLS)


def test_cross_check_rejects_wrong_fits_flag():
    sug = _suggestion(estimated_total_usd=1640.0)
    assert sug.budget is not None
    sug.budget.fits = False
    with pytest.raises(GuardError):
        cross_check(TripResponse(status="ok", suggestion=sug), TOOL_CALLS)


def test_cross_check_rejects_pick_total_from_another_hotels_budget():
    # A grounded compute_budget exists for the Cancun hotel, but the Lisbon pick can't borrow its total.
    cancun_hotels = _call("find_hotels", {"destination": "Cancun"},
                          [{"name": "Beach Inn", "destination": "Cancun", "nightly_usd": 95.0, "tags": []}])
    cancun_budget = _call(
        "compute_budget",
        {"flight_per_person_usd": 400.0, "travelers": 2, "nightly_usd": 95.0, "nights": 7,
         "user_budget_usd": 2000.0, "includes_flights": True},
        {"total_usd": 1465.0, "breakdown": {"flights": 800.0, "hotel": 665.0}, "fits": True,
         "over_by_usd": 0.0, "includes_flights": True},
    )
    resp = TripResponse(status="ok", suggestion=_suggestion(estimated_total_usd=1465.0, budget_total_usd=None))
    with pytest.raises(GuardError, match="estimated total"):
        cross_check(resp, [*TOOL_CALLS, cancun_hotels, cancun_budget])


# ---- (3) pairing: hotel / flight must come from the pick's own destination ----


def test_cross_check_rejects_hotel_from_different_destination():
    porto_hotels = copy.deepcopy(FIND_HOTELS_CALL)
    porto_hotels["args"]["destination"] = "Porto"
    porto_hotels["result"] = [{"name": "Hotel A", "destination": "Porto", "nightly_usd": 120.0, "tags": []}]
    resp = TripResponse(status="ok", suggestion=_suggestion(estimated_total_usd=1640.0))
    with pytest.raises(GuardError, match="hotel"):
        cross_check(resp, [porto_hotels, ESTIMATE_FLIGHTS_CALL, COMPUTE_BUDGET_CALL])


def test_cross_check_rejects_hotel_name_not_returned():
    sug = _suggestion(estimated_total_usd=1640.0)
    assert sug.destinations[0].hotel is not None
    sug.destinations[0].hotel.name = "Hotel Invented"  # price matches, name doesn't
    with pytest.raises(GuardError, match="hotel"):
        cross_check(TripResponse(status="ok", suggestion=sug), TOOL_CALLS)


def test_cross_check_rejects_flight_from_different_destination():
    porto_flight = copy.deepcopy(ESTIMATE_FLIGHTS_CALL)
    porto_flight["args"]["destination"] = "Porto"
    porto_flight["result"]["destination"] = "Porto"
    resp = TripResponse(status="ok", suggestion=_suggestion(estimated_total_usd=1640.0))
    with pytest.raises(GuardError, match="flight"):
        cross_check(resp, [FIND_HOTELS_CALL, porto_flight, COMPUTE_BUDGET_CALL])
