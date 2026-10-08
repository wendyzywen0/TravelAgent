"""Guardrails in Python. Owned by agent C."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from trip_agent import config
from trip_agent.models import BudgetSummary, DestinationPick, TripResponse

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


def _close_opt(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return _close(float(a), float(b))


def _norm(text: Any) -> str:
    return str(text or "").casefold().strip()


@dataclass(frozen=True)
class _HotelSrc:
    places: frozenset[str]   # call args.destination + alias-resolved Hotel.destination, normalized
    name: str                # normalized
    nightly: float


@dataclass(frozen=True)
class _FlightSrc:
    places: frozenset[str]
    per_person: float


@dataclass(frozen=True)
class _BudgetSrc:
    args: dict[str, Any]
    result: dict[str, Any]

    @property
    def total(self) -> float:
        return float(self.result["total_usd"])


def _collect(
    tool_calls: list[dict[str, Any]],
) -> tuple[list[_HotelSrc], list[_FlightSrc], list[_BudgetSrc]]:
    hotels: list[_HotelSrc] = []
    flights: list[_FlightSrc] = []
    budgets: list[_BudgetSrc] = []
    for call in tool_calls:
        if call.get("error"):
            continue
        name = call.get("name")
        result = call.get("result")
        args = call.get("args")
        if result is None or not isinstance(args, dict):
            continue
        if name == "find_hotels" and isinstance(result, list):
            for hotel in result:
                if isinstance(hotel, dict) and "nightly_usd" in hotel and "name" in hotel:
                    places = frozenset(p for p in (_norm(args.get("destination")), _norm(hotel.get("destination"))) if p)
                    hotels.append(_HotelSrc(places, _norm(hotel["name"]), float(hotel["nightly_usd"])))
        elif name == "estimate_flights" and isinstance(result, dict):
            if "round_trip_per_person_usd" in result:
                places = frozenset(p for p in (_norm(args.get("destination")), _norm(result.get("destination"))) if p)
                flights.append(_FlightSrc(places, float(result["round_trip_per_person_usd"])))
        elif name == "compute_budget" and isinstance(result, dict):
            if "total_usd" in result:
                budgets.append(_BudgetSrc(args, result))
    return hotels, flights, budgets


def _budget_args_grounded(b: _BudgetSrc, hotels: list[_HotelSrc], flights: list[_FlightSrc]) -> bool:
    """compute_budget is only a valid source if its inputs came from real tool results."""
    nightly = b.args.get("nightly_usd")
    if nightly is None or not any(_close(float(nightly), h.nightly) for h in hotels):
        return False
    if b.args.get("includes_flights", True):
        fpp = b.args.get("flight_per_person_usd")
        if fpp is None or not any(_close(float(fpp), f.per_person) for f in flights):
            return False
    return True


def _budget_matches(summary: BudgetSummary, b: _BudgetSrc) -> bool:
    r = b.result
    breakdown = r.get("breakdown") or {}
    if set(summary.breakdown) != set(breakdown):
        return False
    if not all(_close(summary.breakdown[k], float(breakdown[k])) for k in breakdown):
        return False
    return (
        _close(summary.total_usd, b.total)
        and summary.fits == r.get("fits")
        and _close_opt(summary.over_by_usd, r.get("over_by_usd"))
        and summary.includes_flights == bool(r.get("includes_flights", True))
    )


def _ungrounded_total_error(label: str, total: float, rejected: list[_BudgetSrc]) -> GuardError:
    for b in rejected:
        if _close(total, b.total):
            return GuardError(
                f"{label} {total} comes from a compute_budget call whose inputs "
                f"(nightly_usd={b.args.get('nightly_usd')}, "
                f"flight_per_person_usd={b.args.get('flight_per_person_usd')}) "
                "match no find_hotels/estimate_flights result."
            )
    return GuardError(f"{label} {total} matches no grounded compute_budget result.")


def _check_pick(
    dest: DestinationPick,
    hotels: list[_HotelSrc],
    flights: list[_FlightSrc],
    valid: list[_BudgetSrc],
    rejected: list[_BudgetSrc],
) -> None:
    place = _norm(dest.name)

    if dest.hotel is not None:
        hname, hnightly = _norm(dest.hotel.name), dest.hotel.nightly_usd
        if not any(place in h.places and h.name == hname and _close(hnightly, h.nightly) for h in hotels):
            raise GuardError(
                f"{dest.name}: hotel {dest.hotel.name!r} at {hnightly}/night matches no find_hotels "
                f"result for {dest.name}."
            )

    if dest.flight_estimate_usd is not None:
        if not any(place in f.places and _close(dest.flight_estimate_usd, f.per_person) for f in flights):
            raise GuardError(
                f"{dest.name}: flight estimate {dest.flight_estimate_usd} matches no estimate_flights "
                f"result for {dest.name}."
            )

    if dest.estimated_total_usd is not None:
        label = f"{dest.name}: estimated total"
        if dest.hotel is None:
            raise GuardError(f"{label} {dest.estimated_total_usd} has no hotel to pair with a compute_budget call.")
        hotel_nightly = dest.hotel.nightly_usd

        def paired(b: _BudgetSrc) -> bool:
            if not _close(float(b.args.get("nightly_usd", -1.0)), hotel_nightly):
                return False
            if b.args.get("includes_flights", True) and dest.flight_estimate_usd is not None:
                return _close(float(b.args.get("flight_per_person_usd", -1.0)), dest.flight_estimate_usd)
            return True

        if not any(paired(b) and _close(dest.estimated_total_usd, b.total) for b in valid):
            raise _ungrounded_total_error(label, dest.estimated_total_usd, rejected)


def cross_check(resp: TripResponse, tool_calls: list[dict[str, Any]]) -> None:
    """Raise GuardError if any dollar figure in resp is not traceable to a tool result.

    - compute_budget calls only count if their nightly/flight inputs came from find_hotels /
      estimate_flights results in the same trace.
    - Each pick's hotel and flight must come from a call for that pick's destination, and its
      total from a compute_budget call that used that pick's hotel price.
    - The budget summary must equal one grounded compute_budget result field for field.
    """
    if resp.status != "ok":
        return
    suggestion = resp.suggestion
    if suggestion is None:
        return

    hotels, flights, budgets = _collect(tool_calls)
    valid = [b for b in budgets if _budget_args_grounded(b, hotels, flights)]
    rejected = [b for b in budgets if b not in valid]

    for dest in suggestion.destinations:
        _check_pick(dest, hotels, flights, valid, rejected)

    summary = suggestion.budget
    if summary is not None and not any(_budget_matches(summary, b) for b in valid):
        if not any(_close(summary.total_usd, b.total) for b in valid):
            raise _ungrounded_total_error("Budget total", summary.total_usd, rejected)
        raise GuardError(
            f"Budget summary (total {summary.total_usd}) does not match any compute_budget result "
            "in breakdown, fits, over_by_usd, or includes_flights."
        )
