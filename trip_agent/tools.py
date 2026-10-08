"""Four mock tools, one per concern. Pure Python, no randomness, no network. Owned by agent B."""
from __future__ import annotations
from pydantic import BaseModel, Field


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


def search_destinations(args: SearchDestinationsArgs) -> list[DestinationCandidate]:
    raise NotImplementedError


def estimate_flights(args: EstimateFlightsArgs) -> FlightEstimate | ToolError:
    raise NotImplementedError


def find_hotels(args: FindHotelsArgs) -> list[Hotel]:
    raise NotImplementedError


def compute_budget(args: ComputeBudgetArgs) -> BudgetResult:
    raise NotImplementedError


# name -> (args model, function). agent.py builds the API tool specs from this and dispatches by name.
TOOLS = {
    "search_destinations": (SearchDestinationsArgs, search_destinations),
    "estimate_flights": (EstimateFlightsArgs, estimate_flights),
    "find_hotels": (FindHotelsArgs, find_hotels),
    "compute_budget": (ComputeBudgetArgs, compute_budget),
}
