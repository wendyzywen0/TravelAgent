"""Deterministic must-have check (SPEC §5.3). Owned by agent A."""
from __future__ import annotations
from dataclasses import dataclass, field
from trip_agent.models import Intent, TripRequest


@dataclass
class GateResult:
    missing: list[str] = field(default_factory=list)      # human-readable field names, e.g. "headcount"
    questions: list[str] = field(default_factory=list)    # one question per missing item, user-facing
    assumptions: list[str] = field(default_factory=list)  # e.g. "Assumed 2 adults (anniversary)"
    request: TripRequest | None = None                    # request with inferred defaults filled in

    @property
    def ok(self) -> bool:
        return not self.missing


QUESTIONS = {
    "travel request": "I suggest trip ideas from one sentence about where or when you'd like to go "
                      "and your budget. What trip can I help you plan?",
    "trip type or timing": "What kind of trip are you after, and when? "
                           "For example, a beach week in February or a city break in Europe this spring.",
    "budget": "Roughly what's your budget in US dollars, and should it cover flights?",
    "headcount": "How many people are travelling (adults, plus any children and their ages)?",
    "trip length": "How many nights do you want to be away, or what are your dates?",
    "origin airport": "Which airport will you be flying from?",
}

# Words that describe price, not the kind of trip; "Cheap." alone is not a trip type.
PRICE_WORDS = {"cheap", "budget", "affordable", "inexpensive", "low-cost", "luxury", "expensive"}
HOTEL_WORDS = ("hotel", "stay", "resort", "accommodation", "airbnb", "villa")


def gate(req: TripRequest) -> GateResult:
    """Apply inference (solo/couple, long weekend, spring break, defaults) then the per-intent table."""
    if not req.is_travel_request:
        return _result(["travel request"], [], req.model_copy(deep=True))

    r = req.model_copy(deep=True)
    assumed: list[str] = []
    prefs = bool(r.region or r.month_or_season or [v for v in r.vibe if v.lower() not in PRICE_WORDS])
    discovery = r.destination is None
    text = " ".join([r.month_or_season or "", r.region or "", *r.vibe]).lower()

    # --- headcount ---
    if r.travelers_adults is None:
        if r.couple_signal:
            r.travelers_adults = 2
            assumed.append("Assumed 2 adults (you mentioned a couple or 'we').")
        elif r.solo_signal:
            r.travelers_adults = 1
            assumed.append("Assumed 1 adult (you're travelling on your own).")
        elif discovery and prefs and r.budget_total_usd is None:
            # Destination discovery default; a total budget needs a real headcount, so we ask instead.
            r.travelers_adults = 2
            assumed.append("Assumed 2 adults since no headcount was given.")
    if r.travelers_children is None:
        r.travelers_children = 0

    # --- trip length ---
    if r.nights is None:
        if "long weekend" in text:
            r.nights = 3
            assumed.append("Assumed 3 nights for a long weekend.")
        elif "spring break" in text:
            r.nights = 7
            assumed.append("Assumed 7 nights for spring break.")
        elif r.start_date and r.end_date and r.end_date > r.start_date:
            r.nights = (r.end_date - r.start_date).days
        elif discovery and prefs:
            r.nights = 7
            assumed.append("Assumed a 7-night trip since no length was given.")

    # --- budget scope and hotel style ---
    has_budget = r.budget_total_usd is not None or r.hotel_nightly_cap_usd is not None
    if r.budget_includes_flights is None:
        r.budget_includes_flights = not r.has_flight_already
        if r.has_flight_already:
            assumed.append("Your flight is already booked, so the budget leaves flights out.")
        elif r.budget_total_usd is not None:
            assumed.append("Assumed your budget includes flights.")
    if r.hotel_style and r.hotel_style.strip().lower() == "nice":
        r.hotel_style = "mid-upper"
        assumed.append("Read 'nice hotel' as mid-to-upper range.")

    r.intents = _intents(r, has_budget)

    # --- must-have table ---
    missing: list[str] = []
    if discovery and not prefs:
        # "Cheap."-style: nothing to go on, so ask for everything we will need at once.
        missing.append("trip type or timing")
        if not has_budget:
            missing.append("budget")
        if r.travelers_adults is None:
            missing.append("headcount")
        if not r.origin_airport and not r.has_flight_already:
            missing.append("origin airport")
    if "accommodation" in r.intents and r.travelers_adults is None:
        missing.append("headcount")
    if "budget" in r.intents:
        if r.travelers_adults is None:
            missing.append("headcount")
        if r.nights is None:
            missing.append("trip length")
        # Flights are only part of the budget when a TOTAL budget is given; a nightly cap alone is hotel-only.
        if r.budget_total_usd is not None and r.budget_includes_flights and not r.has_flight_already and not r.origin_airport:
            missing.append("origin airport")
    return _result(list(dict.fromkeys(missing)), assumed, r)


def _intents(r: TripRequest, has_budget: bool) -> list[Intent]:
    intents: list[Intent] = list(r.intents)
    if not intents:
        hotel_text = " ".join([*r.vibe, *r.must_haves]).lower()
        if r.hotel_style or r.must_haves or r.hotel_nightly_cap_usd is not None or (
            r.destination and any(w in hotel_text for w in HOTEL_WORDS)
        ):
            intents.append("accommodation")
    if has_budget:
        intents.append("budget")
    if r.destination is None:
        intents.insert(0, "destination")
    return list(dict.fromkeys(intents))


def _result(missing: list[str], assumed: list[str], r: TripRequest) -> GateResult:
    return GateResult(missing=missing, questions=[QUESTIONS[m] for m in missing], assumptions=assumed, request=r)
