"""Six live eval cases (SPEC §7.2) plus their Python behavior checks.

Owned by agent D. No API calls happen here - this module only describes cases and
pure functions that score a `TripResponse` (and the trace's tool_call events) already
produced by a run. `evals/run.py` drives the actual `suggest_trip` calls.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple

from trip_agent.models import TripResponse

CheckFn = Callable[[TripResponse, list[dict[str, Any]]], bool]


class Check(NamedTuple):
    label: str
    fn: CheckFn


@dataclass
class EvalCase:
    id: int
    name: str
    input: str
    expected_status: str  # "ok" | "needs_info"
    checks: list[Check] = field(default_factory=list)


def load_tool_calls(trace_path: str | Path) -> list[dict[str, Any]]:
    """Read a trace JSON file and return its tool_call events, in order."""
    data = json.loads(Path(trace_path).read_text())
    return [e for e in data.get("events", []) if e.get("kind") == "tool_call"]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _questions_text(resp: TripResponse) -> str:
    return " ".join(resp.questions).lower()


def _mentions(resp: TripResponse, *any_of: str) -> bool:
    text = _questions_text(resp)
    return any(word in text for word in any_of)


def _tool_called(tool_calls: list[dict[str, Any]], name: str) -> bool:
    return any(tc.get("name") == name for tc in tool_calls)


# Country spellings as they appear in trip_agent/mock_data.py plus the full set named
# in the eval spec, so this check doesn't depend on exactly which countries the mock
# data happens to use today.
EUROPEAN_COUNTRIES = {
    "portugal", "spain", "italy", "france", "denmark", "netherlands", "germany",
    "austria", "czechia", "greece", "croatia", "slovenia", "uk", "united kingdom",
    "ireland", "belgium", "switzerland", "hungary",
}

NEAR_LISBON_COUNTRIES = {"portugal", "spain"}


def _destination_countries_in(resp: TripResponse, allowed: set[str]) -> bool:
    if resp.suggestion is None or not resp.suggestion.destinations:
        return False
    return all(d.country.strip().lower() in allowed for d in resp.suggestion.destinations)


def _no_flights_in_breakdown(resp: TripResponse) -> bool:
    """True when there either is no budget, or the budget's breakdown has no 'flights' key."""
    if resp.suggestion is None or resp.suggestion.budget is None:
        return True
    return "flights" not in resp.suggestion.budget.breakdown


# ---------------------------------------------------------------------------
# Case 1: "Cheap." -> needs_info, asking for everything
# ---------------------------------------------------------------------------

def _c1_budget(resp: TripResponse, tool_calls: list[dict[str, Any]]) -> bool:
    return _mentions(resp, "budget")


def _c1_timing(resp: TripResponse, tool_calls: list[dict[str, Any]]) -> bool:
    return _mentions(resp, "when", "timing", "date")


def _c1_headcount(resp: TripResponse, tool_calls: list[dict[str, Any]]) -> bool:
    return _mentions(resp, "how many", "people", "traveler", "traveller", "headcount")


def _c1_origin(resp: TripResponse, tool_calls: list[dict[str, Any]]) -> bool:
    return _mentions(resp, "from", "airport", "origin")


CASE_1 = EvalCase(
    id=1,
    name="Cheap. (needs everything)",
    input="Cheap.",
    expected_status="needs_info",
    checks=[
        Check("questions mention budget", _c1_budget),
        Check("questions mention timing", _c1_timing),
        Check("questions mention headcount", _c1_headcount),
        Check("questions mention origin", _c1_origin),
    ],
)


# ---------------------------------------------------------------------------
# Case 2: beach week, no headcount -> needs_info, asks headcount, no suggestion
# ---------------------------------------------------------------------------

def _c2_headcount(resp: TripResponse, tool_calls: list[dict[str, Any]]) -> bool:
    return _mentions(resp, "how many", "people", "traveler", "traveller")


def _c2_no_suggestion(resp: TripResponse, tool_calls: list[dict[str, Any]]) -> bool:
    return resp.suggestion is None


CASE_2 = EvalCase(
    id=2,
    name="Beach week, no headcount",
    input="Relaxing beach week in February under $2000, leaving from JFK. Want a nice hotel.",
    expected_status="needs_info",
    checks=[
        Check("a question mentions headcount", _c2_headcount),
        Check("suggestion is None", _c2_no_suggestion),
    ],
)


# ---------------------------------------------------------------------------
# Case 3: beach week for two -> ok, under budget, compute_budget used
# ---------------------------------------------------------------------------

def _c3_under_budget(resp: TripResponse, tool_calls: list[dict[str, Any]]) -> bool:
    if resp.suggestion is None or not resp.suggestion.destinations:
        return False
    return all(
        d.estimated_total_usd is not None and d.estimated_total_usd <= 2000
        for d in resp.suggestion.destinations
    )


def _c3_fits(resp: TripResponse, tool_calls: list[dict[str, Any]]) -> bool:
    return (
        resp.suggestion is not None
        and resp.suggestion.budget is not None
        and resp.suggestion.budget.fits is True
    )


def _c3_compute_budget_called(resp: TripResponse, tool_calls: list[dict[str, Any]]) -> bool:
    return _tool_called(tool_calls, "compute_budget")


CASE_3 = EvalCase(
    id=3,
    name="Beach week for two, under $2000",
    input="Relaxing beach week in February under $2000 for two, leaving from JFK. Want a nice hotel.",
    expected_status="ok",
    checks=[
        Check("every destination estimated_total_usd <= 2000", _c3_under_budget),
        Check("budget.fits is True", _c3_fits),
        Check("compute_budget was called", _c3_compute_budget_called),
    ],
)


# ---------------------------------------------------------------------------
# Case 4: Europe long weekend from SFO -> ok, hotels under $300/night, European
# ---------------------------------------------------------------------------

def _c4_hotel_cap(resp: TripResponse, tool_calls: list[dict[str, Any]]) -> bool:
    if resp.suggestion is None or not resp.suggestion.destinations:
        return False
    return all(
        d.hotel is not None and d.hotel.nightly_usd <= 300
        for d in resp.suggestion.destinations
    )


def _c4_european(resp: TripResponse, tool_calls: list[dict[str, Any]]) -> bool:
    return _destination_countries_in(resp, EUROPEAN_COUNTRIES)


CASE_4 = EvalCase(
    id=4,
    name="Europe long weekend from SFO, boutique under $300/night",
    input=(
        "Long weekend in Europe, flying from SFO. Walkable city, great food, "
        "boutique hotel under $300/night."
    ),
    expected_status="ok",
    checks=[
        Check("every hotel nightly_usd <= 300", _c4_hotel_cap),
        Check("every destination country is European", _c4_european),
    ],
)


# ---------------------------------------------------------------------------
# Case 5: Lisbon add-on, flight already booked -> ok, no estimate_flights call
# ---------------------------------------------------------------------------

def _c5_no_flight_tool(resp: TripResponse, tool_calls: list[dict[str, Any]]) -> bool:
    return not _tool_called(tool_calls, "estimate_flights")


def _c5_near_lisbon(resp: TripResponse, tool_calls: list[dict[str, Any]]) -> bool:
    return _destination_countries_in(resp, NEAR_LISBON_COUNTRIES)


def _c5_no_flights_in_breakdown(resp: TripResponse, tool_calls: list[dict[str, Any]]) -> bool:
    return _no_flights_in_breakdown(resp)


CASE_5 = EvalCase(
    id=5,
    name="Lisbon add-on, flight already booked",
    input=(
        "I'll be in Lisbon Oct 10–13 for a wedding. Want to tack on 5 days somewhere "
        "nearby. Already have the flight to Lisbon."
    ),
    expected_status="ok",
    checks=[
        Check("estimate_flights was not called", _c5_no_flight_tool),
        Check("every destination country is Portugal or Spain", _c5_near_lisbon),
        Check("budget breakdown (if present) has no 'flights' key", _c5_no_flights_in_breakdown),
    ],
)


# ---------------------------------------------------------------------------
# Case 6: Tokyo, excluding flights -> ok, 8 nights, budget excludes flights
# ---------------------------------------------------------------------------

def _c6_budget_excludes_flights(resp: TripResponse, tool_calls: list[dict[str, Any]]) -> bool:
    return resp.suggestion is not None and resp.suggestion.budget is not None and _no_flights_in_breakdown(resp)


def _c6_total_within_budget(resp: TripResponse, tool_calls: list[dict[str, Any]]) -> bool:
    return (
        resp.suggestion is not None
        and resp.suggestion.budget is not None
        and resp.suggestion.budget.total_usd <= 6000
    )


def _c6_nights_eight(resp: TripResponse, tool_calls: list[dict[str, Any]]) -> bool:
    return resp.request is not None and resp.request.nights == 8


CASE_6 = EvalCase(
    id=6,
    name="Tokyo, 8 days, $6k excluding flights",
    input="Tokyo for 8 days in November, two adults, $6k budget excluding flights. We've been once before.",
    expected_status="ok",
    checks=[
        Check("budget present and breakdown has no 'flights' key", _c6_budget_excludes_flights),
        Check("budget.total_usd <= 6000", _c6_total_within_budget),
        Check("request.nights == 8", _c6_nights_eight),
    ],
)


CASES: list[EvalCase] = [CASE_1, CASE_2, CASE_3, CASE_4, CASE_5, CASE_6]
