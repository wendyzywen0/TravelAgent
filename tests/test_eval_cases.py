"""Unit tests for evals/cases.py. No network - these hand-build TripResponse objects and
fake tool_calls lists, then assert the per-case check functions score them correctly."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from trip_agent.models import (
    BudgetSummary,
    DestinationPick,
    HotelPick,
    TripRequest,
    TripResponse,
    TripSuggestion,
)

from evals.cases import CASE_1, CASE_2, CASE_3, CASE_4, CASE_5, CASE_6, CASES, load_tool_calls


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def needs_info(questions: list[str]) -> TripResponse:
    return TripResponse(status="needs_info", questions=questions)


def destination(
    name: str,
    country: str,
    *,
    hotel_nightly: float | None = None,
    flight_pp: float | None = None,
    total: float | None = None,
) -> DestinationPick:
    hotel = HotelPick(name=f"{name} Hotel", nightly_usd=hotel_nightly) if hotel_nightly is not None else None
    return DestinationPick(
        name=name, country=country, why="fits the vibe", hotel=hotel,
        flight_estimate_usd=flight_pp, estimated_total_usd=total,
    )


def ok_response(
    destinations: list[DestinationPick],
    *,
    budget: BudgetSummary | None = None,
    nights: int | None = None,
) -> TripResponse:
    suggestion = TripSuggestion(destinations=destinations, reasoning="grounded in tool results", budget=budget)
    req = TripRequest(nights=nights) if nights is not None else None
    return TripResponse(status="ok", suggestion=suggestion, request=req)


def tool_call(name: str, result: Any = None) -> dict[str, Any]:
    return {"kind": "tool_call", "name": name, "args": {}, "result": result}


def run_checks(case, resp: TripResponse, tool_calls: list[dict[str, Any]]) -> dict[str, bool]:
    return {label: fn(resp, tool_calls) for label, fn in case.checks}


# ---------------------------------------------------------------------------
# CASES list / basic shape
# ---------------------------------------------------------------------------

def test_cases_list_has_six_cases_with_expected_ids_and_status():
    assert [c.id for c in CASES] == [1, 2, 3, 4, 5, 6]
    assert CASES[0].expected_status == "needs_info"
    assert CASES[1].expected_status == "needs_info"
    for c in CASES[2:]:
        assert c.expected_status == "ok"
    for c in CASES:
        assert c.checks, f"case {c.id} has no checks"


# ---------------------------------------------------------------------------
# Case 1: "Cheap."
# ---------------------------------------------------------------------------

def test_case1_all_pass_when_all_topics_covered():
    resp = needs_info([
        "What's your budget in USD?",
        "When are you thinking of travelling?",
        "How many people are travelling?",
        "Which airport would you fly from?",
    ])
    results = run_checks(CASE_1, resp, [])
    assert all(results.values()), results


def test_case1_fails_when_a_topic_is_missing():
    # No mention of headcount at all.
    resp = needs_info(["What's your budget?", "When are you going?", "Which airport?"])
    results = run_checks(CASE_1, resp, [])
    assert results["questions mention headcount"] is False
    assert results["questions mention budget"] is True
    assert results["questions mention timing"] is True
    assert results["questions mention origin"] is True


# ---------------------------------------------------------------------------
# Case 2: beach week, no headcount
# ---------------------------------------------------------------------------

def test_case2_passes_when_headcount_asked_and_no_suggestion():
    resp = needs_info(["How many people are travelling?"])
    results = run_checks(CASE_2, resp, [])
    assert all(results.values()), results


def test_case2_fails_when_headcount_not_asked():
    resp = needs_info(["What's your budget?"])
    results = run_checks(CASE_2, resp, [])
    assert results["a question mentions headcount"] is False
    assert results["suggestion is None"] is True


def test_case2_fails_when_suggestion_present():
    # Status "ok" responses always carry a suggestion; the check should flag that as wrong
    # for this case regardless of what the overall response status happens to be.
    resp = ok_response([destination("Tulum", "Mexico")])
    results = run_checks(CASE_2, resp, [])
    assert results["suggestion is None"] is False


# ---------------------------------------------------------------------------
# Case 3: beach week for two, under $2000
# ---------------------------------------------------------------------------

def _case3_budget(fits: bool, total: float) -> BudgetSummary:
    return BudgetSummary(total_usd=total, user_budget_usd=2000, fits=fits, breakdown={"flights": 760, "hotel": 1190})


def test_case3_passes_within_budget_with_compute_budget_called():
    resp = ok_response(
        [destination("Cancun", "Mexico", hotel_nightly=175, flight_pp=380, total=1950)],
        budget=_case3_budget(True, 1950),
    )
    calls = [tool_call("search_destinations"), tool_call("compute_budget", {"total_usd": 1950})]
    results = run_checks(CASE_3, resp, calls)
    assert all(results.values()), results


def test_case3_fails_when_over_budget():
    resp = ok_response(
        [destination("Barbados", "Barbados", hotel_nightly=360, flight_pp=560, total=2520)],
        budget=_case3_budget(False, 2520),
    )
    calls = [tool_call("compute_budget", {"total_usd": 2520})]
    results = run_checks(CASE_3, resp, calls)
    assert results["every destination estimated_total_usd <= 2000"] is False
    assert results["budget.fits is True"] is False


def test_case3_fails_when_compute_budget_not_called():
    resp = ok_response(
        [destination("Cancun", "Mexico", hotel_nightly=175, flight_pp=380, total=1950)],
        budget=_case3_budget(True, 1950),
    )
    calls = [tool_call("search_destinations")]
    results = run_checks(CASE_3, resp, calls)
    assert results["compute_budget was called"] is False
    assert results["every destination estimated_total_usd <= 2000"] is True


# ---------------------------------------------------------------------------
# Case 4: Europe long weekend from SFO
# ---------------------------------------------------------------------------

def test_case4_passes_cheap_european_boutique_hotel():
    resp = ok_response([destination("Lisbon", "Portugal", hotel_nightly=210)])
    results = run_checks(CASE_4, resp, [])
    assert all(results.values()), results


def test_case4_fails_when_hotel_over_cap():
    resp = ok_response([destination("Copenhagen", "Denmark", hotel_nightly=520)])
    results = run_checks(CASE_4, resp, [])
    assert results["every hotel nightly_usd <= 300"] is False
    assert results["every destination country is European"] is True


def test_case4_fails_when_destination_not_european():
    resp = ok_response([destination("Tokyo", "Japan", hotel_nightly=220)])
    results = run_checks(CASE_4, resp, [])
    assert results["every destination country is European"] is False


# ---------------------------------------------------------------------------
# Case 5: Lisbon add-on, flight already booked
# ---------------------------------------------------------------------------

def test_case5_passes_near_lisbon_no_flight_tool_no_flights_in_budget():
    resp = ok_response(
        [destination("Lagos", "Portugal", hotel_nightly=190)],
        budget=BudgetSummary(total_usd=950, breakdown={"hotel": 950}, includes_flights=False),
    )
    calls = [tool_call("search_destinations"), tool_call("find_hotels")]
    results = run_checks(CASE_5, resp, calls)
    assert all(results.values()), results


def test_case5_fails_when_estimate_flights_called():
    resp = ok_response([destination("Seville", "Spain", hotel_nightly=160)])
    calls = [tool_call("estimate_flights", {"round_trip_per_person_usd": 300})]
    results = run_checks(CASE_5, resp, calls)
    assert results["estimate_flights was not called"] is False


def test_case5_fails_when_destination_outside_portugal_spain():
    resp = ok_response([destination("Bologna", "Italy", hotel_nightly=190)])
    results = run_checks(CASE_5, resp, [])
    assert results["every destination country is Portugal or Spain"] is False


def test_case5_fails_when_budget_breakdown_has_flights_key():
    resp = ok_response(
        [destination("Lagos", "Portugal", hotel_nightly=190)],
        budget=BudgetSummary(total_usd=1500, breakdown={"flights": 550, "hotel": 950}),
    )
    results = run_checks(CASE_5, resp, [])
    assert results["budget breakdown (if present) has no 'flights' key"] is False


# ---------------------------------------------------------------------------
# Case 6: Tokyo, 8 days, $6k excluding flights
# ---------------------------------------------------------------------------

def test_case6_passes_eight_nights_excluding_flights_within_budget():
    resp = ok_response(
        [destination("Tokyo", "Japan", hotel_nightly=220)],
        budget=BudgetSummary(total_usd=1760, breakdown={"hotel": 1760}, includes_flights=False),
        nights=8,
    )
    results = run_checks(CASE_6, resp, [])
    assert all(results.values()), results


def test_case6_fails_when_breakdown_includes_flights():
    resp = ok_response(
        [destination("Tokyo", "Japan", hotel_nightly=220)],
        budget=BudgetSummary(total_usd=2500, breakdown={"flights": 740, "hotel": 1760}),
        nights=8,
    )
    results = run_checks(CASE_6, resp, [])
    assert results["budget present and breakdown has no 'flights' key"] is False


def test_case6_fails_when_over_budget():
    resp = ok_response(
        [destination("Tokyo", "Japan", hotel_nightly=220)],
        budget=BudgetSummary(total_usd=7000, breakdown={"hotel": 7000}, includes_flights=False),
        nights=8,
    )
    results = run_checks(CASE_6, resp, [])
    assert results["budget.total_usd <= 6000"] is False


def test_case6_fails_when_nights_not_eight():
    resp = ok_response(
        [destination("Tokyo", "Japan", hotel_nightly=220)],
        budget=BudgetSummary(total_usd=1760, breakdown={"hotel": 1760}, includes_flights=False),
        nights=5,
    )
    results = run_checks(CASE_6, resp, [])
    assert results["request.nights == 8"] is False


def test_case6_fails_when_request_missing():
    resp = ok_response(
        [destination("Tokyo", "Japan", hotel_nightly=220)],
        budget=BudgetSummary(total_usd=1760, breakdown={"hotel": 1760}, includes_flights=False),
    )
    results = run_checks(CASE_6, resp, [])
    assert results["request.nights == 8"] is False


# ---------------------------------------------------------------------------
# load_tool_calls
# ---------------------------------------------------------------------------

def test_load_tool_calls_filters_and_preserves_order(tmp_path: Path):
    trace = {
        "request_id": "abc12345",
        "input": "Tokyo for 8 days...",
        "events": [
            {"kind": "input", "raw_input": "Tokyo for 8 days..."},
            {"kind": "gate", "ok": True},
            {"kind": "tool_call", "name": "search_destinations", "args": {}, "result": []},
            {"kind": "model_call", "model": "claude-opus-4-8"},
            {"kind": "tool_call", "name": "compute_budget", "args": {}, "result": {"total_usd": 1760}},
            {"kind": "final", "response": {}},
        ],
        "usage": [],
        "totals": {},
    }
    path = tmp_path / "trace.json"
    path.write_text(json.dumps(trace))

    calls = load_tool_calls(path)
    assert [c["name"] for c in calls] == ["search_destinations", "compute_budget"]
    assert all(c["kind"] == "tool_call" for c in calls)


def test_load_tool_calls_empty_when_no_tool_calls(tmp_path: Path):
    trace = {"events": [{"kind": "input", "raw_input": "Cheap."}, {"kind": "gate", "ok": False}]}
    path = tmp_path / "trace.json"
    path.write_text(json.dumps(trace))

    assert load_tool_calls(path) == []


def test_load_tool_calls_accepts_str_path(tmp_path: Path):
    trace = {"events": [{"kind": "tool_call", "name": "find_hotels", "args": {}, "result": []}]}
    path = tmp_path / "trace.json"
    path.write_text(json.dumps(trace))

    calls = load_tool_calls(str(path))
    assert len(calls) == 1 and calls[0]["name"] == "find_hotels"
