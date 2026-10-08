"""AC1: the gate on the seven sample inputs of SPEC §5.3 (plus the no-headcount beach case)."""
from datetime import date

from trip_agent.gate import gate
from trip_agent.models import TripRequest


def has(assumptions: list[str], *words: str) -> bool:
    return any(all(w.lower() in a.lower() for w in words) for a in assumptions)


def beach(**overrides) -> TripRequest:
    # "Relaxing beach week in February under $2000 for two, leaving from JFK. Want a nice hotel."
    base = dict(
        intents=["destination", "accommodation", "budget"], origin_airport="JFK",
        vibe=["beach", "relaxing"], month_or_season="February", nights=7, travelers_adults=2,
        budget_total_usd=2000, hotel_style="nice",
    )
    return TripRequest(**{**base, **overrides})


def test_beach_for_two_ok():
    g = gate(beach())
    assert g.ok and g.missing == [] and g.questions == []
    assert g.request is not None and g.request.hotel_style == "mid-upper"
    assert has(g.assumptions, "nice")
    assert g.request.budget_includes_flights is True


def test_beach_without_headcount_asks_headcount():
    g = gate(beach(travelers_adults=None))
    assert not g.ok
    assert g.missing == ["headcount"]
    assert len(g.questions) == 1 and "how many" in g.questions[0].lower()


def test_europe_long_weekend_ok_with_assumptions():
    # "Long weekend somewhere in Europe from SFO, boutique hotel under $300/night."
    req = TripRequest(
        intents=["destination", "accommodation", "budget"], origin_airport="SFO",
        region="Europe", month_or_season="long weekend", hotel_style="boutique",
        hotel_nightly_cap_usd=300,
    )
    g = gate(req)
    assert g.ok, g.missing
    assert g.request is not None
    assert g.request.travelers_adults == 2 and g.request.nights == 3
    assert has(g.assumptions, "2 adults") and has(g.assumptions, "3 nights")


def test_family_spring_break_needs_origin():
    # "Family of 4 (kids 6 and 9), spring break, somewhere warm, ~$5k all-in, need a pool."
    req = TripRequest(
        intents=["destination", "accommodation", "budget"], travelers_adults=2,
        travelers_children=2, children_ages=[6, 9], budget_total_usd=5000,
        vibe=["warm"], month_or_season="spring break", must_haves=["pool"],
    )
    g = gate(req)
    assert not g.ok
    assert g.missing == ["origin airport"]
    assert "airport" in g.questions[0].lower()
    assert g.request is not None and g.request.nights == 7 and g.request.budget_includes_flights is True
    assert has(g.assumptions, "7 nights")


def test_anniversary_needs_origin_and_assumes_two_adults():
    # "Anniversary trip in May, not Santorini, flag anything past $4k."
    req = TripRequest(
        intents=["destination", "budget"], couple_signal=True, month_or_season="May",
        exclusions=["Santorini"], budget_total_usd=4000,
    )
    g = gate(req)
    assert not g.ok
    assert g.missing == ["origin airport"]
    assert has(g.assumptions, "2 adults")
    assert g.request is not None and g.request.travelers_adults == 2


def test_lisbon_flight_booked_ok_with_one_adult():
    # "I'll be in Lisbon Oct 10-13 for work, then want 5 days somewhere nearby. Flight already booked."
    req = TripRequest(
        intents=["destination", "accommodation"], solo_signal=True, destination="Lisbon",
        region="near Lisbon", has_flight_already=True, nights=5,
        start_date=date(2026, 10, 10), end_date=date(2026, 10, 13),
    )
    g = gate(req)
    assert g.ok, g.missing
    assert g.request is not None
    assert g.request.travelers_adults == 1 and g.request.nights == 5
    assert g.request.budget_includes_flights is False
    assert has(g.assumptions, "1 adult")


def test_tokyo_ok():
    # "Tokyo, 8 days in November, 2 adults, $6k excluding flights."
    req = TripRequest(
        intents=["accommodation", "budget"], destination="Tokyo", month_or_season="November",
        nights=8, travelers_adults=2, budget_total_usd=6000, budget_includes_flights=False,
    )
    g = gate(req)
    assert g.ok, g.missing
    assert g.assumptions == []


def test_cheap_needs_everything():
    for req in (TripRequest(vibe=["cheap"]), TripRequest()):
        g = gate(req)
        assert not g.ok
        assert set(g.missing) == {"trip type or timing", "budget", "headcount", "origin airport"}
        text = " ".join(g.questions).lower()
        for word in ("what kind of trip", "when", "budget", "how many", "airport"):
            assert word in text
        assert g.request is not None and g.request.nights is None and g.request.travelers_adults is None


def test_off_topic():
    g = gate(TripRequest(is_travel_request=False))
    assert g.missing == ["travel request"]
    assert len(g.questions) == 1 and "trip" in g.questions[0].lower()


def test_missing_items_are_deduped_and_one_question_each():
    req = TripRequest(intents=["accommodation", "budget"], destination="Paris", budget_total_usd=3000)
    g = gate(req)
    assert g.missing == ["headcount", "trip length", "origin airport"]
    assert len(g.questions) == len(g.missing)


def test_nights_from_dates_and_intent_inference():
    req = TripRequest(
        destination="Rome", start_date=date(2026, 5, 1), end_date=date(2026, 5, 5),
        travelers_adults=2, hotel_nightly_cap_usd=200, origin_airport="BOS",
    )
    g = gate(req)
    assert g.ok, g.missing
    assert g.request is not None and g.request.nights == 4
    assert g.request.intents == ["accommodation", "budget"]


def test_input_not_mutated():
    req = beach(travelers_adults=None, couple_signal=True)
    gate(req)
    assert req.travelers_adults is None and req.hotel_style == "nice"
