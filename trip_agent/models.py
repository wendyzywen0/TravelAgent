"""Typed contract. Every other module builds against these shapes. Do not change signatures without the lead."""
from __future__ import annotations
from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, model_validator

Intent = Literal["destination", "accommodation", "budget"]


class TripRequest(BaseModel):
    """What the model extracts from the user's text. Unknown = None / empty."""
    intents: list[Intent] = Field(default_factory=list)
    origin_airport: str | None = None
    destination: str | None = None          # a fixed place the user named
    region: str | None = None               # e.g. "Europe", "near Lisbon"
    vibe: list[str] = Field(default_factory=list)   # e.g. ["beach", "relaxing"]
    month_or_season: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    nights: int | None = None
    travelers_adults: int | None = None
    travelers_children: int | None = None
    children_ages: list[int] = Field(default_factory=list)
    budget_total_usd: float | None = None
    budget_includes_flights: bool | None = None
    hotel_nightly_cap_usd: float | None = None
    hotel_style: str | None = None          # e.g. "boutique", "nice", "family"
    must_haves: list[str] = Field(default_factory=list)   # e.g. ["pool"]
    exclusions: list[str] = Field(default_factory=list)   # e.g. ["Santorini"]
    has_flight_already: bool = False
    is_travel_request: bool = True          # False => off-topic
    solo_signal: bool = False               # "I'll be", "I'm going" with no other headcount
    couple_signal: bool = False             # "we", "anniversary", "couple", "honeymoon"


class HotelPick(BaseModel):
    name: str
    nightly_usd: float
    tags: list[str] = Field(default_factory=list)


class DestinationPick(BaseModel):
    name: str
    country: str
    why: str
    hotel: HotelPick | None = None
    flight_estimate_usd: float | None = None   # round trip, per person
    estimated_total_usd: float | None = None   # flights + hotel for the whole party


class BudgetSummary(BaseModel):
    total_usd: float
    user_budget_usd: float | None = None
    fits: bool | None = None
    over_by_usd: float | None = None
    breakdown: dict[str, float] = Field(default_factory=dict)   # keys: "flights", "hotel"
    includes_flights: bool = True


class TripSuggestion(BaseModel):
    destinations: list[DestinationPick] = Field(min_length=1, max_length=3)
    reasoning: str
    budget: BudgetSummary | None = None
    caveats: list[str] = Field(default_factory=list)


class TripResponse(BaseModel):
    status: Literal["ok", "needs_info"]
    questions: list[str] = Field(default_factory=list)
    suggestion: TripSuggestion | None = None
    assumptions: list[str] = Field(default_factory=list)
    request: TripRequest | None = None      # what was extracted, for transparency
    trace_path: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> "TripResponse":
        if self.status == "needs_info":
            if not self.questions:
                raise ValueError("needs_info requires at least one question")
            if self.suggestion is not None:
                raise ValueError("needs_info must not carry a suggestion")
        else:
            if self.suggestion is None:
                raise ValueError("ok requires a suggestion")
            if self.questions:
                raise ValueError("ok must not carry questions")
        return self
