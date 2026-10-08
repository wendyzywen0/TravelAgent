"""Unit tests for the mock tools (AC2, AC3, AC4 plus coverage for the eval cases). No API calls."""
from __future__ import annotations

import pytest

from trip_agent.mock_data import DESTINATIONS, FLIGHTS, HOTELS
from trip_agent.tools import (

    TOOLS,
    BudgetResult,
    ComputeBudgetArgs,
    EstimateFlightsArgs,
    FindHotelsArgs,
    FlightEstimate,
    SearchDestinationsArgs,
    ToolError,
    compute_budget,
    estimate_flights,
    find_hotels,
    search_destinations,
)


def _ok_budget(args):
    """compute_budget for the happy path: narrows away ToolError so attribute access type-checks."""
    from trip_agent.tools import BudgetResult, ToolError, compute_budget
    out = compute_budget(args)
    assert not isinstance(out, ToolError), out
    assert isinstance(out, BudgetResult)
    return out



def _names(**kwargs: object) -> list[str]:
    return [d.name for d in search_destinations(SearchDestinationsArgs.model_validate(kwargs))]


# --- AC2: compute_budget ------------------------------------------------------------------

def test_budget_fits_with_flights() -> None:
    # 2 x 420 flights = 840; 7 x 150 hotel = 1050; total 1890 <= 2000.
    r = _ok_budget(ComputeBudgetArgs(flight_per_person_usd=420, travelers=2, nightly_usd=150,
                                         nights=7, user_budget_usd=2000))
    assert r == BudgetResult(total_usd=1890.0, breakdown={"flights": 840.0, "hotel": 1050.0},
                             fits=True, over_by_usd=0.0, includes_flights=True)


def test_budget_over_with_exact_over_by() -> None:
    # 2 x 480 = 960; 7 x 260 = 1820; total 2780; over 2000 by 780.
    r = _ok_budget(ComputeBudgetArgs(flight_per_person_usd=480, travelers=2, nightly_usd=260,
                                         nights=7, user_budget_usd=2000))
    assert r.total_usd == 2780.0
    assert r.breakdown == {"flights": 960.0, "hotel": 1820.0}
    assert r.fits is False
    assert r.over_by_usd == 780.0


def test_budget_excluding_flights_has_no_flight_line() -> None:
    # Tokyo: 8 x 220 = 1760, flights excluded even though a fare is passed in.
    r = _ok_budget(ComputeBudgetArgs(flight_per_person_usd=980, travelers=2, nightly_usd=220,
                                         nights=8, user_budget_usd=6000, includes_flights=False))
    assert "flights" not in r.breakdown
    assert r.breakdown == {"hotel": 1760.0}
    assert r.total_usd == 1760.0
    assert r.fits is True
    assert r.over_by_usd == 0.0
    assert r.includes_flights is False


def test_budget_without_user_budget_and_rounding() -> None:
    r = _ok_budget(ComputeBudgetArgs(flight_per_person_usd=333.335, travelers=3,
                                         nightly_usd=99.999, nights=3))
    assert r.breakdown == {"flights": 1000.0, "hotel": 300.0}
    assert r.total_usd == 1300.0
    assert r.fits is None and r.over_by_usd is None


# --- AC3: exclusions ------------------------------------------------------------------------

def test_romantic_search_without_exclusion_returns_santorini() -> None:
    assert "Santorini" in _names(vibe=["romantic"])


@pytest.mark.parametrize("exclusion", ["Santorini", "santorini", "SANTORINI", "Santorini, Greece"])
def test_excluded_santorini_never_returned(exclusion: str) -> None:
    variants: list[dict[str, object]] = [
        {"vibe": ["romantic"]},
        {"vibe": ["beach"]},
        {"vibe": ["romantic", "beach"], "region": "Europe"},
        {"region": "Europe"},
        {"vibe": ["nothing-matches-this"]},  # exercises the vibe fallback path
        {},
    ]
    for kwargs in variants:
        assert "Santorini" not in _names(**kwargs, exclusions=[exclusion]), kwargs


# --- AC4: hotel caps and must-haves ---------------------------------------------------------

@pytest.mark.parametrize("cap", [100.0, 150.0, 200.0, 299.99, 300.0, 400.0])
def test_no_hotel_above_cap_anywhere(cap: float) -> None:
    for dest in HOTELS:
        for style in [None, "boutique", "luxury", "nice", "family"]:
            hotels = find_hotels(FindHotelsArgs(destination=dest, style=style, nightly_cap_usd=cap))
            assert all(h.nightly_usd <= cap for h in hotels), (dest, style, cap)


def test_cap_is_inclusive() -> None:
    hotels = find_hotels(FindHotelsArgs(destination="Copenhagen", style="boutique", nightly_cap_usd=295))
    assert [h.name for h in hotels] == ["Nyhavn Loft Hotel"]


def test_pool_must_have_honored() -> None:
    for dest in HOTELS:
        for h in find_hotels(FindHotelsArgs(destination=dest, must_haves=["pool"])):
            assert "pool" in h.tags
    # Lisbon's only pool hotel is above 300, so pool + cap 300 yields nothing (cap is never relaxed).
    assert find_hotels(FindHotelsArgs(destination="Lisbon", nightly_cap_usd=300, must_haves=["pool"])) == []


def test_hotels_sorted_and_case_insensitive() -> None:
    hotels = find_hotels(FindHotelsArgs(destination="punta CANA"))
    assert [h.nightly_usd for h in hotels] == sorted(h.nightly_usd for h in hotels)
    assert all(h.destination == "Punta Cana" for h in hotels)


def test_every_europe_city_has_boutique_under_300_and_a_hotel_above() -> None:
    for d in DESTINATIONS:
        if d["region"] != "europe":
            continue
        boutique = find_hotels(FindHotelsArgs(destination=d["name"], style="boutique", nightly_cap_usd=300))
        assert any("boutique" in h.tags for h in boutique), d["name"]
        assert any(h["nightly_usd"] > 300 for h in HOTELS[d["name"]]), d["name"]


# --- estimate_flights -----------------------------------------------------------------------

def test_known_flight_pair_case_insensitive() -> None:
    r = estimate_flights(EstimateFlightsArgs(origin="jfk", destination="punta cana", month="February"))
    assert r == FlightEstimate(origin="JFK", destination="Punta Cana", round_trip_per_person_usd=420.0, hours=4.0)


def test_unknown_flight_pair_returns_tool_error() -> None:
    r = estimate_flights(EstimateFlightsArgs(origin="LAX", destination="Tokyo"))
    assert isinstance(r, ToolError)
    assert r.error == "no fare data for LAX→Tokyo"
    assert isinstance(estimate_flights(EstimateFlightsArgs(origin="JFK", destination="Atlantis")), ToolError)


def test_flight_coverage_for_eval_cases() -> None:
    beach = [d["name"] for d in DESTINATIONS if d["region"] in ("caribbean", "mexico")]
    europe = [d["name"] for d in DESTINATIONS if d["region"] == "europe"]
    for name in beach:
        assert ("JFK", name) in FLIGHTS
    for name in europe:
        assert ("SFO", name) in FLIGHTS
    for pair in [("JFK", "Tokyo"), ("SFO", "Tokyo"), ("JFK", "Lisbon"), ("JFK", "Porto")]:
        assert pair in FLIGHTS


# --- search_destinations: regions, seasons, eval coverage -----------------------------------

def test_europe_search_returns_only_europe() -> None:
    results = search_destinations(SearchDestinationsArgs(vibe=["walkable", "food"], region="Europe"))
    assert results
    assert all(d.region == "europe" and "europe" in d.tags for d in results)
    assert len(results) <= 6


def test_near_lisbon_search() -> None:
    results = search_destinations(SearchDestinationsArgs(region="near Lisbon", season="October"))
    assert results
    assert all(d.region == "near-lisbon" or "near-lisbon" in d.tags for d in results)
    assert "Lisbon" not in [d.name for d in results]


def test_february_beach_search_is_warm_and_sorted() -> None:
    results = search_destinations(SearchDestinationsArgs(vibe=["beach"], season="February"))
    assert results
    assert all("warm" in d.tags and "beach" in d.tags for d in results)
    keys = [(d.price_level, d.name) for d in results]
    assert keys == sorted(keys)


def test_vibe_without_match_falls_back_to_region() -> None:
    results = search_destinations(SearchDestinationsArgs(vibe=["skiing"], region="Caribbean"))
    assert results and all(d.region == "caribbean" for d in results)


def test_two_jfk_beach_picks_fit_2000_for_two_for_seven_nights() -> None:
    fitting: list[str] = []
    for d in search_destinations(SearchDestinationsArgs(vibe=["beach", "warm"], season="February")):
        fare = estimate_flights(EstimateFlightsArgs(origin="JFK", destination=d.name))
        if isinstance(fare, ToolError):
            continue
        pool_hotels = find_hotels(FindHotelsArgs(destination=d.name, must_haves=["pool"]))
        if not pool_hotels:
            continue
        budget = _ok_budget(ComputeBudgetArgs(
            flight_per_person_usd=fare.round_trip_per_person_usd, travelers=2,
            nightly_usd=pool_hotels[0].nightly_usd, nights=7, user_budget_usd=2000))
        if budget.fits:
            fitting.append(d.name)
    assert len(fitting) >= 2, fitting


def test_tokyo_eight_nights_fits_6000_but_luxury_does_not() -> None:
    hotels = find_hotels(FindHotelsArgs(destination="Tokyo"))
    nightly = {h.name: h.nightly_usd for h in hotels}
    ok = _ok_budget(ComputeBudgetArgs(travelers=2, nightly_usd=nightly["Shibuya Stream Hotel"], nights=8,
                                          user_budget_usd=6000, includes_flights=False))
    lux = _ok_budget(ComputeBudgetArgs(travelers=2, nightly_usd=nightly["Marunouchi Imperial"], nights=8,
                                           user_budget_usd=6000, includes_flights=False))
    assert ok.fits is True
    assert lux.fits is False and lux.over_by_usd == 800.0


def test_tools_mapping_intact() -> None:
    assert set(TOOLS) == {"search_destinations", "estimate_flights", "find_hotels", "compute_budget"}


def test_compute_budget_refuses_zero_fare_when_flights_included():
    from trip_agent.tools import ComputeBudgetArgs, ToolError, compute_budget
    out = compute_budget(ComputeBudgetArgs(flight_per_person_usd=0.0, travelers=2, nightly_usd=240, nights=7,
                                           user_budget_usd=2000, includes_flights=True))
    assert isinstance(out, ToolError) and "includes_flights=false" in out.error
    ok = compute_budget(ComputeBudgetArgs(flight_per_person_usd=0.0, travelers=2, nightly_usd=240, nights=7,
                                          user_budget_usd=2000, includes_flights=False))
    assert not isinstance(ok, ToolError) and ok.total_usd == 1680.0 and "flights" not in ok.breakdown
