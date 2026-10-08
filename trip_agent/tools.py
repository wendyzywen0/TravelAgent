"""Four mock tools, one per concern. Pure Python, no randomness, no network. Owned by agent B."""
from __future__ import annotations
import re
import unicodedata

from pydantic import BaseModel, Field

from trip_agent.mock_data import (
    DESTINATION_ALIASES,
    DESTINATIONS,
    FLIGHTS,
    HOTELS,
    DestinationRow,
)


class SearchDestinationsArgs(BaseModel):
    vibe: list[str] = Field(default_factory=list)
    season: str | None = None
    region: str | None = None
    exclusions: list[str] = Field(default_factory=list)


class DestinationCandidate(BaseModel):
    name: str
    country: str
    region: str
    price_level: int = Field(ge=1, le=3)
    tags: list[str]
    typical_nightly_usd: float


class EstimateFlightsArgs(BaseModel):
    origin: str
    destination: str
    month: str | None = None


class FlightEstimate(BaseModel):
    origin: str
    destination: str
    round_trip_per_person_usd: float
    hours: float


class FindHotelsArgs(BaseModel):
    destination: str
    style: str | None = None
    nightly_cap_usd: float | None = None
    must_haves: list[str] = Field(default_factory=list)


class Hotel(BaseModel):
    name: str
    destination: str
    nightly_usd: float
    tags: list[str]


class ComputeBudgetArgs(BaseModel):
    flight_per_person_usd: float = 0.0
    travelers: int = Field(ge=1)
    nightly_usd: float
    nights: int = Field(ge=1)
    user_budget_usd: float | None = None
    includes_flights: bool = True


class BudgetResult(BaseModel):
    total_usd: float
    breakdown: dict[str, float]   # {"flights": ..., "hotel": ...}; no "flights" key when excluded
    fits: bool | None
    over_by_usd: float | None
    includes_flights: bool


class ToolError(BaseModel):
    error: str


def _norm(text: str) -> str:
    """Casefold, strip accents and surrounding whitespace."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold().strip()


def _resolve_destination(query: str) -> str | None:
    """Map a free-text destination to a canonical mock_data name, or None."""
    q = _norm(query)
    if not q:
        return None
    by_norm = {_norm(d["name"]): d["name"] for d in DESTINATIONS}
    if q in by_norm:
        return by_norm[q]
    if q in DESTINATION_ALIASES:
        return DESTINATION_ALIASES[q]
    # e.g. "Lisbon, Portugal" or "Lagos (Algarve)"
    for key, name in by_norm.items():
        if key in q:
            return name
    for alias, name in DESTINATION_ALIASES.items():
        if alias in q:
            return name
    return None


_VIBE_SYNONYMS: dict[str, str] = {
    "sun": "warm", "sunny": "warm", "hot": "warm", "tropical": "warm", "tropics": "warm",
    "beaches": "beach", "ocean": "beach", "sea": "beach", "island": "beach", "islands": "beach",
    "relax": "relaxing", "relaxed": "relaxing", "chill": "relaxing", "calm": "relaxing",
    "quiet": "relaxing", "laid-back": "relaxing", "unwind": "relaxing",
    "romance": "romantic", "honeymoon": "romantic", "couple": "romantic", "couples": "romantic",
    "walking": "walkable", "walk": "walkable", "pedestrian": "walkable",
    "foodie": "food", "cuisine": "food", "restaurants": "food", "eating": "food", "great food": "food",
    "urban": "city", "cities": "city",
    "museums": "culture", "history": "culture", "art": "culture", "cultural": "culture",
    "kids": "family", "family-friendly": "family", "kid-friendly": "family",
    "off the beaten path": "non-touristy", "offbeat": "non-touristy", "untouristy": "non-touristy",
    "hidden gem": "non-touristy", "not touristy": "non-touristy", "non touristy": "non-touristy",
    "coast": "coastal", "seaside": "coastal",
    "hiking": "nature", "outdoors": "nature",
}


def _vibe_terms(vibes: list[str]) -> set[str]:
    terms: set[str] = set()
    for raw in vibes:
        v = _norm(raw)
        if not v:
            continue
        candidates: list[str] = [v, *(w for w in re.split(r"[\s,/]+", v) if w)]
        for c in candidates:
            terms.add(_VIBE_SYNONYMS.get(c, c))
    return terms


_REGION_ALIASES: dict[str, str] = {
    "europe": "europe", "european": "europe",
    "caribbean": "caribbean",
    "mexico": "mexico",
    "asia": "asia", "japan": "asia",
}


def _region_match(query: str, dest: DestinationRow) -> bool:
    q = _norm(query)
    if "lisbon" in q:  # "near Lisbon", "around Lisbon", "near-lisbon"
        return dest["region"] == "near-lisbon" or "near-lisbon" in dest["tags"]
    if "portugal" in q and dest["country"] == "Portugal":
        return True
    wanted = {region for alias, region in _REGION_ALIASES.items() if alias in q}
    if wanted:
        return dest["region"] in wanted
    # Fall back to a country/region substring match ("Spain", "Greece", ...).
    return _norm(dest["country"]) in q or _norm(dest["region"]) in q


_MONTH_NAMES: dict[str, int] = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_SEASONS: dict[str, set[int]] = {
    "winter": {12, 1, 2}, "spring": {3, 4, 5}, "summer": {6, 7, 8},
    "fall": {9, 10, 11}, "autumn": {9, 10, 11},
}


def _season_months(season: str | None) -> set[int]:
    """Months named in a free-text season ("February", "Feb", "winter", "Oct 10-13"). Empty = unknown."""
    if not season:
        return set()
    months: set[int] = set()
    for word in re.findall(r"[a-z]+", _norm(season)):
        if word in _SEASONS:
            months |= _SEASONS[word]
        elif len(word) >= 3:
            months |= {num for full, num in _MONTH_NAMES.items() if full.startswith(word)}
    return months


def _is_excluded(dest: DestinationRow, exclusions: list[str]) -> bool:
    name = _norm(dest["name"])
    country = _norm(dest["country"])
    for raw in exclusions:
        ex = _norm(raw)
        if not ex:
            continue
        if ex == name or ex == country or name in ex:
            return True
        if DESTINATION_ALIASES.get(ex) == dest["name"]:
            return True
    return False


def _to_candidate(d: DestinationRow) -> DestinationCandidate:
    return DestinationCandidate(
        name=d["name"], country=d["country"], region=d["region"], price_level=d["price_level"],
        tags=list(d["tags"]), typical_nightly_usd=float(d["typical_nightly_usd"]),
    )


_MAX_DESTINATIONS = 6


def search_destinations(args: SearchDestinationsArgs) -> list[DestinationCandidate]:
    # Exclusions are a hard filter and are applied first, so no fallback can bring them back.
    pool = [d for d in DESTINATIONS if not _is_excluded(d, args.exclusions)]
    if args.region:
        pool = [d for d in pool if _region_match(args.region, d)]
    months = _season_months(args.season)
    if months:
        in_season = [d for d in pool if months & set(d["best_months"])]
        if in_season:
            pool = in_season
    terms = _vibe_terms(args.vibe)
    if terms:
        matched = [d for d in pool if terms & set(d["tags"])]
        if matched:  # otherwise fall back to region/season-only results
            pool = matched
    pool.sort(key=lambda d: (d["price_level"], d["name"]))
    return [_to_candidate(d) for d in pool[:_MAX_DESTINATIONS]]


def estimate_flights(args: EstimateFlightsArgs) -> FlightEstimate | ToolError:
    origin = args.origin.strip().upper()
    dest = _resolve_destination(args.destination)
    fare = FLIGHTS.get((origin, dest)) if dest else None
    if fare is None:
        return ToolError(error=f"no fare data for {origin}→{args.destination.strip()}")
    return FlightEstimate(
        origin=origin, destination=dest or args.destination,
        round_trip_per_person_usd=float(fare["round_trip_per_person_usd"]), hours=float(fare["hours"]),
    )


_STYLE_TAGS: dict[str, str] = {
    "boutique": "boutique",
    "luxury": "luxury", "luxe": "luxury", "5-star": "luxury", "five-star": "luxury",
    "family": "family", "family-friendly": "family", "kid-friendly": "family",
    "nice": "mid-upper", "upscale": "mid-upper", "mid-upper": "mid-upper", "upper-mid": "mid-upper",
    "comfortable": "mid-upper", "midrange": "mid-upper", "mid-range": "mid-upper",
    "budget": "budget", "cheap": "budget", "affordable": "budget",
    "beachfront": "beachfront", "beach": "beachfront",
}

_MUST_HAVE_TAGS: dict[str, str] = {
    "swimming pool": "pool", "pools": "pool",
    "beach": "beachfront", "beach access": "beachfront", "on the beach": "beachfront",
    "kids": "family", "family-friendly": "family", "kid-friendly": "family",
}


def find_hotels(args: FindHotelsArgs) -> list[Hotel]:
    dest = _resolve_destination(args.destination)
    if dest is None:
        return []
    rows = HOTELS.get(dest, [])
    # Hard constraints: nightly cap and must-haves. Never relaxed.
    if args.nightly_cap_usd is not None:
        cap = args.nightly_cap_usd
        rows = [h for h in rows if h["nightly_usd"] <= cap]
    needed = {_MUST_HAVE_TAGS.get(_norm(m), _norm(m)) for m in args.must_haves if _norm(m)}
    rows = [h for h in rows if needed <= set(h["tags"])]
    # Soft preference: style. If nothing matches the style, keep the hard-filtered list.
    if args.style:
        style_tag = _STYLE_TAGS.get(_norm(args.style), _norm(args.style))
        styled = [h for h in rows if style_tag in h["tags"]]
        if styled:
            rows = styled
    rows = sorted(rows, key=lambda h: (h["nightly_usd"], h["name"]))
    return [Hotel(name=h["name"], destination=dest, nightly_usd=float(h["nightly_usd"]), tags=list(h["tags"]))
            for h in rows]


def compute_budget(args: ComputeBudgetArgs) -> BudgetResult | ToolError:
    breakdown: dict[str, float] = {}
    if args.includes_flights and args.flight_per_person_usd <= 0:
        return ToolError(error="flight_per_person_usd must be a fare returned by estimate_flights when includes_flights is true. "
                               "If estimate_flights returned no data for this destination, call compute_budget again with includes_flights=false "
                               "for a hotel-only total, set that destination's flight_estimate_usd to null, and say so in caveats.")
    if args.includes_flights:
        breakdown["flights"] = round(args.flight_per_person_usd * args.travelers, 2)
    breakdown["hotel"] = round(args.nightly_usd * args.nights, 2)
    total = round(sum(breakdown.values()), 2)
    if args.user_budget_usd is None:
        fits: bool | None = None
        over_by: float | None = None
    else:
        fits = total <= args.user_budget_usd
        over_by = round(max(0.0, total - args.user_budget_usd), 2)
    return BudgetResult(
        total_usd=total, breakdown=breakdown, fits=fits, over_by_usd=over_by,
        includes_flights=args.includes_flights,
    )


# name -> (args model, function). agent.py builds the API tool specs from this and dispatches by name.
TOOLS = {
    "search_destinations": (SearchDestinationsArgs, search_destinations),
    "estimate_flights": (EstimateFlightsArgs, estimate_flights),
    "find_hotels": (FindHotelsArgs, find_hotels),
    "compute_budget": (ComputeBudgetArgs, compute_budget),
}
