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
3. **Budget planning** — estimate a total from flights and accommodation only, and say whether it fits the user's figure. Food, activities and ground transport are out of scope for the initial version; the response says so in a caveat.

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
- "Anniversary" / "couple" / "honeymoon" / "we" ⇒ infer 2 adults with a caveat.
- First-person singular ("I'll be in Lisbon", "I'm going") with no other headcount signal ⇒ infer 1 adult with a caveat.
- "Long weekend" ⇒ 3 nights; "spring break" ⇒ 7 nights. Both assumed with a caveat, not asked.
- Budget planning is in play whenever the user gives a dollar figure or cap.
- `budget_includes_flights` defaults to true unless the user says "excluding flights" or already has the flight.

Expected outcome on the seven sample inputs:

| Input | Expected status | Why |
|---|---|---|
| Beach week, Feb, <$2000 for two, JFK, nice hotel | ok | all fields present |
| Long weekend Europe, SFO, boutique <$300/night | ok | headcount assumed 2 |
| Family of 4, spring break, ~$5k all-in, pool | needs_info | no origin, budget includes flights |
| Anniversary May, not Santorini, flag past $4k | needs_info | no origin; headcount inferred 2 |
| Lisbon Oct 10–13 + 5 days nearby, flight booked | ok | flights excluded; "I'll be" ⇒ 1 adult inferred |
| Tokyo 8 days Nov, 2 adults, $6k excl. flights | ok | all fields present |
| "Cheap." | needs_info | nothing known |

### 5.4 Tools (D4) — all mock, all Python

| Tool | Input | Output | Notes |
|---|---|---|---|
| `search_destinations` | vibe[], season, region, exclusions[] | list of candidates: name, country, price_level (1–3), tags, typical_nightly_usd | hardcoded table of ~12 destinations |
| `estimate_flights` | origin, destination, month | round-trip fare per person (usd), hours | hardcoded fares for a handful of pairs; unknown pairs return a "no data" error the model must surface as a caveat |
| `find_hotels` | destination, style, nightly_cap | list of hotels: name, nightly_usd, tags (pool, boutique, …) | hardcoded ~3 per destination |
| `compute_budget` | flight_pp, travelers, nightly, nights, user_budget, includes_flights | total, breakdown (flights, hotel), fits, over_by | pure arithmetic, no randomness; covers flights + hotel only |

- Tool errors are returned to the model as error results, not raised.
- The model never does arithmetic; it must call `compute_budget`.

### 5.5 Prompting and model

- Model: `claude-opus-4-8` for the agent and the judge (D4, D6). Adaptive thinking, low or
  medium effort; exact setting chosen at implementation.
- Call 1 and the final answer use structured output so parsing never depends on prose.
- System prompt states: do not invent prices; use the tools; if a tool returns no data, say so.

### 5.6 Guardrails (basic, all in Python)

- **Input.** Reject empty input or input over 2,000 characters with a clear error, before any model call.
- **Prompt injection.** The user text is passed as data inside the user message, never into the system prompt. The system prompt says instructions in the request are travel preferences, not commands.
- **Loop.** Hard cap of 6 model turns in call 2. Each tool call's arguments are validated with pydantic before the tool runs; bad arguments return an error result to the model, never an exception.
- **Output.** The final answer must parse into `TripResponse`. Every dollar figure in the response is re-checked against tool results: totals must equal a `compute_budget` result, hotel prices must match `find_hotels` output, flight fares must match `estimate_flights` output. A mismatch fails the response with a clear error rather than returning a made-up number.
- **Scope.** If the request is not about travel, return `needs_info` with one question saying what the agent does.
- **Cost.** Each model call sets `max_tokens`; the runner tracks cumulative tokens and refuses to start a new eval run if the project ledger is past $10.

### 5.7 Logging and tracing

- Every request gets a short `request_id`.
- A trace records, in order: the raw input, call 1 output (the `TripRequest`), the gate decision and missing fields, every tool call with arguments, result, and duration, every model call with model, effort, input/output tokens, and duration, and the final response or error.
- Traces are written as one JSON file per request under `traces/` (git-ignored). The CLI prints the trace path at the end. `--verbose` also streams the trace events to stderr as they happen.
- Standard `logging` at INFO for the summary lines (gate decision, tool names called, token totals), DEBUG for full payloads.
- The eval report links each case to its trace file so a failing case can be opened and read.

## 6. Constraints

- Python 3.12+ (machine has 3.14), `uv` for setup, `anthropic` + `pydantic` only runtime deps.
- API key read from `ANTHROPIC_API_KEY`, falling back to `~/tokens/.anthropic_api_key`. Never committed.
- Tool loop hard cap: 6 model turns. On cap, return `ok` with whatever is grounded plus a caveat, or `needs_info` if nothing is.
- Every `estimated_total_usd` shown must equal a `compute_budget` result (checked in Python before returning).
- No network calls except the Anthropic API. No randomness in mocks.
- `tests/` must run in under 5 seconds with no key set.
- Total token spend for the whole project (building, demo, evals, optional sweep) stays under $10. The eval runner prints token usage and estimated cost per run and appends to a simple ledger file.
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

### 7.3 Guardrails and tracing (`tests/`, no API)
- AC11. Empty input and input over 2,000 chars raise a clear error without a model call.
- AC12. A response whose `estimated_total_usd` does not match any `compute_budget` result is rejected.
- AC13. A tool call with invalid arguments returns an error result and the loop continues.
- AC14. Running the CLI on any input writes one JSON trace file containing the input, the gate decision, every tool call, and token usage.

### 7.4 README
- AC15. A fresh clone reaches a working `suggest_trip` call in under 5 minutes following only the README.
- AC16. README explains, in a few lines each: tool split, orchestration choice, missing-info policy, eval dimensions, and what was cut.

## 8. Unresolved questions (flagged, not answered)

1. **Loop-cap fallback.** If the model hits 6 turns without a final answer, return partial `ok` with caveats or `needs_info`? Proposal in 6 is a placeholder.
2. ~~Default daily spend.~~ Resolved: budget covers flights + accommodation only. Food and activities are excluded from the initial scope and named in a caveat.
3. ~~"Long weekend" and "spring break" lengths.~~ Resolved: 3 nights and 7 nights, assumed with a caveat.
4. ~~Headcount for the Lisbon case.~~ Resolved: "I'll be in Lisbon" signals one person ⇒ infer 1 adult with a caveat.
5. **Judge effort and prompt wording.** Low effort was agreed; the rubric text itself is not yet written.
6. **Structured-output mechanism.** `output_config.format` vs a single `strict` tool for the final answer. Implementation detail, but it affects how tool calls and the final answer coexist in call 2.
7. ~~Eval cost ceiling.~~ Resolved: under $10 total for the whole project. Runner reports usage per run.
