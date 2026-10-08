# TravelAgent — Specification

Status: agreed design, not yet implemented. Decisions trace to `DECISIONS.md` (D1–D7).
Date: 2026-10-08. Budget: a focused 2 hours including evaluation and submission.

## 1. Problem

Build a small "Trip Idea" agent: a single-turn function that takes a natural-language travel
request and returns a structured suggestion. The agent reasons about destinations, budget,
flights and accommodation using mock tools. When the request lacks what is needed to make a
recommendation, the agent asks clarifying questions instead of guessing.

## 2. Intended users

- **Primary:** a traveler who types a loose request ("beach week in February under $2000 for two")
  and wants a short, honest shortlist with rough costs and caveats.
- **Secondary:** the reviewer of this exercise, who wants to see how the tools are sliced, how
  the loop is orchestrated, how missing info is handled, and how quality is measured.

## 3. Scope

The agent handles one or more of three jobs per request (D2):

1. **Destination discovery** — suggest 1–3 destinations that match the vibe, season, region.
2. **Accommodation discovery** — suggest hotels for a known or newly chosen destination.
3. **Budget planning** — estimate a total and say whether it fits the user's figure.

Deliverables (D7):

- A Python package with one entry function `suggest_trip(text: str) -> TripResponse` and a
  one-line CLI.
- Typed request and response models (pydantic).
- Four mock tools, one per concern (D4).
- A deterministic gate for missing critical info (D1, D3).
- `tests/` — fast unit tests, no API calls (D5).
- `evals/` — six live eval cases, three scoring dimensions, summary report (D6, D7).
- `README.md` — runnable in under 5 minutes.

## 4. Explicitly excluded

From the brief:
- Real travel data or third-party travel APIs. Mocks only, hardcoded for a handful of inputs.
- Any UI beyond a CLI.
- Persistence, sessions, multi-turn conversation. The user re-sends a fuller prompt if asked.
- Authentication, accounts, users.
- Deployment, caching, observability, retries.

From our decisions (D7), deferred unless time remains after verification:
- Smaller-model sweep (Sonnet 5, Haiku 4.5).
- A seventh eval case (anniversary).
- Wider mock data.

## 5. Expected behavior

### 5.1 Flow (D4)

```
text
  │
  ▼
[Call 1] model extracts TripRequest (structured output; unknown fields are null)
  │
  ▼
[Python gate] apply the must-have table (5.3) to the detected intents
  │
  ├─ missing critical fields ──▶ TripResponse(status="needs_info", questions=[...])   (no call 2)
  │
  ▼
[Call 2] tool loop, max ~6 steps, model chooses among 4 tools
  │
  ▼
[Python checks] budget totals, caps, exclusions re-verified on the final answer
  │
  ▼
TripResponse(status="ok", suggestion=TripSuggestion)
```

### 5.2 Typed models (field names are the proposal; exact types are set at implementation)

`TripRequest` (output of call 1)
- `intents: list["destination" | "accommodation" | "budget"]`
- `origin_airport: str | null`
- `destination: str | null` — a fixed place the user named
- `region: str | null` — e.g. "Europe", "near Lisbon"
- `vibe: list[str]` — e.g. ["beach", "relaxing"], may be empty
- `month_or_season: str | null`
- `start_date, end_date: date | null`
- `nights: int | null`
- `travelers_adults, travelers_children: int | null`, `children_ages: list[int]`
- `budget_total_usd: float | null`, `budget_includes_flights: bool | null`
- `hotel_nightly_cap_usd: float | null`, `hotel_style: str | null`
- `must_haves: list[str]` — e.g. ["pool"]
- `exclusions: list[str]` — e.g. ["Santorini"]
- `has_flight_already: bool`

`TripResponse`
- `status: "ok" | "needs_info"`
- `questions: list[str]` — non-empty only when `needs_info`
- `suggestion: TripSuggestion | null` — present only when `ok`
- `assumptions: list[str]` — what was inferred (e.g. "assumed 2 adults")

`TripSuggestion`
- `destinations: list[DestinationPick]` (1–3), each with `name`, `why`, `hotel: HotelPick | null`,
  `flight_estimate_usd: float | null`, `estimated_total_usd: float | null`
- `reasoning: str` — grounded in tool results
- `budget: BudgetSummary | null` — `total_usd`, `user_budget_usd`, `fits: bool`, `breakdown`
- `caveats: list[str]`

### 5.3 Must-have table (D3) — enforced in Python

| Job | Must have, or we ask | Assume with a caveat |
|---|---|---|
| Destination discovery | At least one of: vibe, region, season | 2 adults, 7 nights |
| Accommodation discovery | A destination (given or chosen in the same run), headcount | dates; "nice" = mid-upper |
| Budget planning | budget figure, headcount, trip length, and origin airport if flights are in the budget | nothing |

Rules:
- All missing critical fields are asked at once, in one response.
- "Anniversary" / "couple" / "honeymoon" ⇒ infer 2 adults with a caveat.
- Budget planning is in play whenever the user gives a dollar figure or cap.
- `budget_includes_flights` defaults to true unless the user says "excluding flights" or already has the flight.

Expected outcome on the seven sample inputs:

| Input | Expected status | Why |
|---|---|---|
| Beach week, Feb, <$2000 for two, JFK, nice hotel | ok | all fields present |
| Long weekend Europe, SFO, boutique <$300/night | ok | headcount assumed 2 |
| Family of 4, spring break, ~$5k all-in, pool | needs_info | no origin, budget includes flights |
| Anniversary May, not Santorini, flag past $4k | needs_info | no origin; headcount inferred 2 |
| Lisbon Oct 10–13 + 5 days nearby, flight booked | ok | flights excluded; headcount assumed |
| Tokyo 8 days Nov, 2 adults, $6k excl. flights | ok | all fields present |
| "Cheap." | needs_info | nothing known |

### 5.4 Tools (D4) — all mock, all Python

| Tool | Input | Output | Notes |
|---|---|---|---|
| `search_destinations` | vibe[], season, region, exclusions[] | list of candidates: name, country, price_level (1–3), tags, typical_nightly_usd | hardcoded table of ~12 destinations |
| `estimate_flights` | origin, destination, month | round-trip fare per person (usd), hours | hardcoded fares for a handful of pairs; unknown pairs return a "no data" error the model must surface as a caveat |
| `find_hotels` | destination, style, nightly_cap | list of hotels: name, nightly_usd, tags (pool, boutique, …) | hardcoded ~3 per destination |
| `compute_budget` | flight_pp, travelers, nightly, nights, daily_spend_pp, user_budget, includes_flights | total, breakdown, fits, over_by | pure arithmetic, no randomness |

- Tool errors are returned to the model as error results, not raised.
- The model never does arithmetic; it must call `compute_budget`.

### 5.5 Prompting and model

- Model: `claude-opus-4-8` for the agent and the judge (D4, D6). Adaptive thinking, low or
  medium effort; exact setting chosen at implementation.
- Call 1 and the final answer use structured output so parsing never depends on prose.
- System prompt states: do not invent prices; use the tools; if a tool returns no data, say so.

## 6. Constraints

- Python 3.12+ (machine has 3.14), `uv` for setup, `anthropic` + `pydantic` only runtime deps.
- API key read from `ANTHROPIC_API_KEY`, falling back to `~/tokens/.anthropic_api_key`. Never committed.
- Tool loop hard cap: 6 model turns. On cap, return `ok` with whatever is grounded plus a caveat, or `needs_info` if nothing is.
- Every `estimated_total_usd` shown must equal a `compute_budget` result (checked in Python before returning).
- No network calls except the Anthropic API. No randomness in mocks.
- `tests/` must run in under 5 seconds with no key set.
- README setup path: clone → `uv sync` → set key → one command to run, one to test, one to eval.

## 7. Acceptance criteria (testable)

### 7.1 Unit tests (`tests/`, no API)
- AC1. `gate(TripRequest(...))` returns the expected missing-field list for each row of 5.3's sample table (seven cases).
- AC2. `compute_budget` returns exact totals for three hand-computed cases, including `fits=False` with correct `over_by`.
- AC3. `search_destinations` honors exclusions (Santorini never returned when excluded).
- AC4. `find_hotels` never returns a hotel above `nightly_cap`.
- AC5. `TripResponse` with `status="needs_info"` must have `questions` non-empty and `suggestion=None`; the reverse for `ok`. Validation enforces this.

### 7.2 Eval cases (`evals/`, live, six cases, D7)
Each case is scored on Structure (pass/fail), Behavior (per-check pass/fail), Fit (judge 1–5).

| # | Case | Behavior checks |
|---|---|---|
| 1 | "Cheap." | status `needs_info`; questions mention budget, timing, headcount, origin |
| 2 | Beach week, Feb, <$2000, JFK, no headcount | `needs_info`; a question mentions headcount; no destinations |
| 3 | Beach week for two, <$2000, JFK | `ok`; every `estimated_total_usd` ≤ 2000; `budget.fits` true; `compute_budget` was called |
| 4 | Europe long weekend from SFO, boutique <$300/night | `ok`; every hotel `nightly_usd` ≤ 300; destination tagged Europe |
| 5 | Lisbon Oct 10–13 + 5 days nearby, flight booked | `ok`; `estimate_flights` not called; suggestion is near Lisbon |
| 6 | Tokyo 8 days Nov, $6k excl. flights | `ok`; budget breakdown has no flight line; nights = 8; total ≤ 6000 |

- AC6. The eval runner prints a table: one row per case, the three scores, per-dimension averages.
- AC7. Structure passes on 6/6. Behavior passes on at least 5/6. Mean Fit ≥ 3.5. (Targets; the report shows actuals.)
- AC8. The judge sees the request, the tool results, and the final answer; it scores only vibe match and groundedness, nothing Python already checked.

### 7.3 README
- AC9. A fresh clone reaches a working `suggest_trip` call in under 5 minutes following only the README.
- AC10. README explains, in a few lines each: tool split, orchestration choice, missing-info policy, eval dimensions, and what was cut.

## 8. Unresolved questions (flagged, not answered)

1. **Loop-cap fallback.** If the model hits 6 turns without a final answer, return partial `ok` with caveats or `needs_info`? Proposal in 6 is a placeholder.
2. **Default daily spend.** `compute_budget` needs a per-person daily spend for food/activities. A flat default (e.g. $100/day) is an invented number; should it be a tool input the model sets from price_level instead?
3. **"Long weekend" and "spring break" lengths.** Treat as 3 nights and 7 nights? Or ask? Today they'd be assumed with a caveat.
4. **Headcount for the Lisbon case.** The sample gives no headcount and asks for accommodation; by the D3 table that would ask, but D7 expects `ok`. Decide: assume 1 adult (solo wedding guest), or ask.
5. **Judge effort and prompt wording.** Low effort was agreed; the rubric text itself is not yet written.
6. **Structured-output mechanism.** `output_config.format` vs a single `strict` tool for the final answer. Implementation detail, but it affects how tool calls and the final answer coexist in call 2.
7. **Eval cost ceiling.** No dollar cap set per eval run. Six cases × up to 7 calls on Opus 4.8 is small but not zero.
