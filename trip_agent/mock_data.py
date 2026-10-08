"""Hardcoded mock travel data used by trip_agent.tools. All prices in USD. No randomness.

Owned by agent B. Other modules may read DESTINATIONS (e.g. for destination names).
"""
from __future__ import annotations

from typing import TypedDict


class DestinationRow(TypedDict):
    name: str
    country: str
    region: str  # one of: caribbean, mexico, europe, near-lisbon, asia
    price_level: int  # 1 (cheap) .. 3 (pricey)
    tags: list[str]
    typical_nightly_usd: float
    best_months: list[int]  # 1..12, months when this place is a good pick


class HotelRow(TypedDict):
    name: str
    nightly_usd: float
    tags: list[str]  # subset of: pool, boutique, beachfront, family, luxury, mid-upper, budget


class FareRow(TypedDict):
    round_trip_per_person_usd: float
    hours: float


_ALL_YEAR = list(range(1, 13))
_CARIB_WINTER = [11, 12, 1, 2, 3, 4]
_EU_WARM = [4, 5, 6, 7, 8, 9, 10]

DESTINATIONS: list[DestinationRow] = [
    # --- Beach, warm in February, reachable from JFK ---
    {"name": "Cancun", "country": "Mexico", "region": "mexico", "price_level": 1,
     "tags": ["beach", "relaxing", "warm", "family", "food"],
     "typical_nightly_usd": 160, "best_months": _CARIB_WINTER},
    {"name": "Punta Cana", "country": "Dominican Republic", "region": "caribbean", "price_level": 1,
     "tags": ["beach", "relaxing", "warm", "family"],
     "typical_nightly_usd": 150, "best_months": _CARIB_WINTER},
    {"name": "Aruba", "country": "Aruba", "region": "caribbean", "price_level": 2,
     "tags": ["beach", "relaxing", "warm", "family"],
     "typical_nightly_usd": 250, "best_months": _ALL_YEAR},
    {"name": "Barbados", "country": "Barbados", "region": "caribbean", "price_level": 3,
     "tags": ["beach", "relaxing", "warm", "romantic"],
     "typical_nightly_usd": 380, "best_months": _CARIB_WINTER},
    # --- Europe: walkable, great food, boutique hotels ---
    {"name": "Lisbon", "country": "Portugal", "region": "europe", "price_level": 2,
     "tags": ["walkable", "food", "city", "boutique", "europe", "culture"],
     "typical_nightly_usd": 200, "best_months": _EU_WARM},
    {"name": "Porto", "country": "Portugal", "region": "europe", "price_level": 1,
     "tags": ["walkable", "food", "city", "boutique", "europe", "near-lisbon", "culture"],
     "typical_nightly_usd": 150, "best_months": _EU_WARM},
    {"name": "Barcelona", "country": "Spain", "region": "europe", "price_level": 2,
     "tags": ["walkable", "food", "city", "boutique", "europe", "coastal", "culture"],
     "typical_nightly_usd": 240, "best_months": _EU_WARM},
    {"name": "Bologna", "country": "Italy", "region": "europe", "price_level": 2,
     "tags": ["walkable", "food", "city", "boutique", "europe", "non-touristy"],
     "typical_nightly_usd": 200, "best_months": [3, 4, 5, 6, 9, 10, 11]},
    {"name": "Copenhagen", "country": "Denmark", "region": "europe", "price_level": 3,
     "tags": ["walkable", "food", "city", "boutique", "europe", "design"],
     "typical_nightly_usd": 360, "best_months": [5, 6, 7, 8, 9]},
    {"name": "Puglia", "country": "Italy", "region": "europe", "price_level": 2,
     "tags": ["romantic", "food", "relaxing", "non-touristy", "coastal", "europe"],
     "typical_nightly_usd": 220, "best_months": [5, 6, 7, 8, 9, 10]},
    {"name": "Santorini", "country": "Greece", "region": "europe", "price_level": 3,
     "tags": ["romantic", "beach", "relaxing", "europe"],
     "typical_nightly_usd": 400, "best_months": [5, 6, 7, 8, 9, 10]},
    # --- Near Lisbon (reachable by train/bus/short hop) ---
    {"name": "Lagos", "country": "Portugal", "region": "near-lisbon", "price_level": 2,
     "tags": ["beach", "relaxing", "near-lisbon", "europe", "algarve"],
     "typical_nightly_usd": 200, "best_months": [5, 6, 7, 8, 9, 10]},
    {"name": "Cascais", "country": "Portugal", "region": "near-lisbon", "price_level": 2,
     "tags": ["coastal", "walkable", "romantic", "near-lisbon", "europe", "sintra"],
     "typical_nightly_usd": 230, "best_months": _EU_WARM},
    {"name": "Madeira", "country": "Portugal", "region": "near-lisbon", "price_level": 2,
     "tags": ["nature", "relaxing", "warm", "near-lisbon", "europe"],
     "typical_nightly_usd": 200, "best_months": _ALL_YEAR},
    {"name": "Seville", "country": "Spain", "region": "near-lisbon", "price_level": 1,
     "tags": ["walkable", "food", "city", "culture", "warm", "near-lisbon", "europe"],
     "typical_nightly_usd": 160, "best_months": [3, 4, 5, 9, 10, 11]},
    # --- Asia ---
    {"name": "Tokyo", "country": "Japan", "region": "asia", "price_level": 2,
     "tags": ["city", "food", "culture", "walkable"],
     "typical_nightly_usd": 230, "best_months": [3, 4, 5, 10, 11]},
]

# Other names people use for a destination -> canonical DESTINATIONS name.
DESTINATION_ALIASES: dict[str, str] = {
    "cancun": "Cancun",
    "riviera maya": "Cancun",
    "tulum": "Cancun",
    "dominican republic": "Punta Cana",
    "algarve": "Lagos",
    "sintra": "Cascais",
    "funchal": "Madeira",
    "sevilla": "Seville",
    "bari": "Puglia",
    "apulia": "Puglia",
    "oia": "Santorini",
}

HOTELS: dict[str, list[HotelRow]] = {
    "Cancun": [
        {"name": "Hotel Mar Azul", "nightly_usd": 140, "tags": ["pool", "budget", "family"]},
        {"name": "Riviera Maya Sands Resort", "nightly_usd": 175,
         "tags": ["pool", "mid-upper", "beachfront", "family"]},
        {"name": "Casa Coral Boutique", "nightly_usd": 320, "tags": ["boutique", "beachfront", "luxury"]},
    ],
    "Punta Cana": [
        {"name": "Bavaro Palms Hotel", "nightly_usd": 120, "tags": ["pool", "budget", "family"]},
        {"name": "Punta Cana Breeze Resort", "nightly_usd": 150,
         "tags": ["pool", "mid-upper", "beachfront", "family"]},
        {"name": "Cap Cana Grand", "nightly_usd": 420, "tags": ["pool", "luxury", "beachfront"]},
    ],
    "Aruba": [
        {"name": "Palm Beach Inn", "nightly_usd": 190, "tags": ["pool", "budget"]},
        {"name": "Eagle Beach Suites", "nightly_usd": 260,
         "tags": ["pool", "mid-upper", "beachfront", "family"]},
        {"name": "Aruba Royal Shores", "nightly_usd": 480, "tags": ["pool", "luxury", "beachfront"]},
    ],
    "Barbados": [
        {"name": "Bridgetown Guesthouse", "nightly_usd": 210, "tags": ["budget"]},
        {"name": "Platinum Coast Hotel", "nightly_usd": 360, "tags": ["pool", "mid-upper", "beachfront"]},
        {"name": "Sandy Cove Retreat", "nightly_usd": 750, "tags": ["pool", "luxury", "beachfront"]},
    ],
    "Lisbon": [
        {"name": "Baixa Budget Rooms", "nightly_usd": 95, "tags": ["budget"]},
        {"name": "Alfama Patio Boutique", "nightly_usd": 210, "tags": ["boutique", "mid-upper"]},
        {"name": "Chiado Grand Hotel", "nightly_usd": 380, "tags": ["luxury", "pool"]},
    ],
    "Porto": [
        {"name": "Bolhao Rooms", "nightly_usd": 80, "tags": ["budget"]},
        {"name": "Ribeira Wine House", "nightly_usd": 165, "tags": ["boutique", "mid-upper"]},
        {"name": "Douro Palace Porto", "nightly_usd": 340, "tags": ["luxury", "pool"]},
    ],
    "Barcelona": [
        {"name": "Gothic Quarter Inn", "nightly_usd": 130, "tags": ["budget"]},
        {"name": "Gracia Courtyard Hotel", "nightly_usd": 260, "tags": ["boutique", "mid-upper"]},
        {"name": "Eixample Modernista Suites", "nightly_usd": 420, "tags": ["luxury", "pool"]},
    ],
    "Bologna": [
        {"name": "Due Torri Budget", "nightly_usd": 110, "tags": ["budget"]},
        {"name": "Portici Boutique Hotel", "nightly_usd": 190, "tags": ["boutique", "mid-upper"]},
        {"name": "Palazzo Felsina", "nightly_usd": 330, "tags": ["luxury"]},
    ],
    "Copenhagen": [
        {"name": "Vesterbro Rooms", "nightly_usd": 210, "tags": ["budget"]},
        {"name": "Nyhavn Loft Hotel", "nightly_usd": 295, "tags": ["boutique"]},
        {"name": "Kongens Grand", "nightly_usd": 520, "tags": ["luxury", "mid-upper"]},
    ],
    "Puglia": [
        {"name": "Trulli Rooms", "nightly_usd": 120, "tags": ["budget"]},
        {"name": "Masseria Ulivo", "nightly_usd": 240, "tags": ["boutique", "pool", "mid-upper"]},
        {"name": "Polignano Cliff Hotel", "nightly_usd": 390, "tags": ["luxury", "pool"]},
    ],
    "Santorini": [
        {"name": "Kamari Beach Rooms", "nightly_usd": 140, "tags": ["budget", "beachfront"]},
        {"name": "Fira View Hotel", "nightly_usd": 230, "tags": ["boutique", "pool"]},
        {"name": "Oia Caldera Suites", "nightly_usd": 450, "tags": ["luxury", "pool"]},
    ],
    "Lagos": [
        {"name": "Lagos Old Town Guesthouse", "nightly_usd": 110, "tags": ["budget", "boutique"]},
        {"name": "Ponta da Piedade Hotel", "nightly_usd": 190,
         "tags": ["pool", "mid-upper", "beachfront", "family"]},
        {"name": "Algarve Cliffs Resort", "nightly_usd": 350, "tags": ["pool", "luxury", "beachfront"]},
    ],
    "Cascais": [
        {"name": "Cascais Bay Boutique", "nightly_usd": 230, "tags": ["boutique", "beachfront"]},
        {"name": "Sintra Quinta Retreat", "nightly_usd": 310, "tags": ["luxury", "pool"]},
    ],
    "Madeira": [
        {"name": "Funchal Garden Hotel", "nightly_usd": 170, "tags": ["pool", "mid-upper", "family"]},
        {"name": "Madeira Cliff Resort", "nightly_usd": 360, "tags": ["pool", "luxury"]},
    ],
    "Seville": [
        {"name": "Triana Budget Hostal", "nightly_usd": 85, "tags": ["budget"]},
        {"name": "Santa Cruz Patio Hotel", "nightly_usd": 160, "tags": ["boutique", "mid-upper"]},
        {"name": "Alcazar Palace Hotel", "nightly_usd": 340, "tags": ["luxury", "pool"]},
    ],
    "Tokyo": [
        {"name": "Asakusa Budget Inn", "nightly_usd": 110, "tags": ["budget"]},
        {"name": "Shibuya Stream Hotel", "nightly_usd": 220, "tags": ["mid-upper"]},
        {"name": "Ginza Boutique House", "nightly_usd": 290, "tags": ["boutique"]},
        {"name": "Marunouchi Imperial", "nightly_usd": 850, "tags": ["luxury", "pool"]},
    ],
}

# (ORIGIN airport code, canonical destination name) -> round-trip fare per person.
FLIGHTS: dict[tuple[str, str], FareRow] = {
    # JFK -> beach
    ("JFK", "Cancun"): {"round_trip_per_person_usd": 380, "hours": 4.0},
    ("JFK", "Punta Cana"): {"round_trip_per_person_usd": 420, "hours": 4.0},
    ("JFK", "Aruba"): {"round_trip_per_person_usd": 480, "hours": 4.5},
    ("JFK", "Barbados"): {"round_trip_per_person_usd": 560, "hours": 4.75},
    # SFO -> Europe
    ("SFO", "Lisbon"): {"round_trip_per_person_usd": 820, "hours": 13.5},
    ("SFO", "Porto"): {"round_trip_per_person_usd": 860, "hours": 15.0},
    ("SFO", "Barcelona"): {"round_trip_per_person_usd": 780, "hours": 13.5},
    ("SFO", "Bologna"): {"round_trip_per_person_usd": 900, "hours": 15.0},
    ("SFO", "Copenhagen"): {"round_trip_per_person_usd": 840, "hours": 12.5},
    ("SFO", "Puglia"): {"round_trip_per_person_usd": 950, "hours": 16.0},
    ("SFO", "Santorini"): {"round_trip_per_person_usd": 1050, "hours": 17.0},
    # JFK -> Portugal
    ("JFK", "Lisbon"): {"round_trip_per_person_usd": 620, "hours": 7.0},
    ("JFK", "Porto"): {"round_trip_per_person_usd": 650, "hours": 7.5},
    # Tokyo
    ("JFK", "Tokyo"): {"round_trip_per_person_usd": 1250, "hours": 14.0},
    ("SFO", "Tokyo"): {"round_trip_per_person_usd": 980, "hours": 11.0},
}
