# TravelAgent — decisions log

Agreed during the planning interview on 2026-10-08. One request in, one response out.

## D1. Missing critical info → ask, in the response
- The response has a status: `ok` (suggestions) or `needs_info` (clarifying questions, no destinations).
- Single turn only. The user is expected to re-send a fuller prompt with the answers.
- What counts as "critical" is decided by Python rules, not by the model, so it is deterministic and testable.
- Softer gaps get an assumption plus a caveat, not a question.

## D2. "Critical" depends on the user's intent
- Initial scope: the agent can do one or more of three jobs — destination discovery, accommodation discovery, budget planning.
- The model extracts intent(s) and fields into a typed request object (nullable fields). Python then checks which must-have fields are missing for the detected intent(s).
- Example: "Relaxing beach week in February under $2000, leaving from JFK. Want a nice hotel." → budget planning is in play, headcount is missing → ask.
- All missing critical fields are asked in one response (single turn, so batch the questions).
- Per-intent required-field table: see D3.

## D3. Per-intent must-have fields (checked in Python)
| Job | Must have, or we ask | Assume with a caveat |
|---|---|---|
| Destination discovery | At least one preference: vibe, region, or season | Headcount (2 adults), duration (1 week) |
| Accommodation discovery | A destination (given, or picked in the same run), headcount | Dates, style ("nice" = mid-upper) |
| Budget planning | A budget figure, headcount, trip length, and origin airport when flights are part of the budget | Nothing else |

- Origin is strict for all-in budgets: "$5k all-in" with no origin → ask.
- "Anniversary" implies 2 travelers (inferred, with caveat), but a missing origin still asks.
- Expected outcome on the 7 sample inputs: "Cheap.", the family-of-4 one, and the anniversary one ask for clarification; the other four get suggestions.
- "Cheap." and similar ambiguous inputs → `needs_info` listing what is needed (trip type, timing, budget, headcount, origin).

## D4. Orchestration: gate, then bounded tool loop
- Call 1: model extracts a typed `TripRequest` (intents, fields, nulls) via structured output.
- Python gate applies D3. If anything critical is missing → return `needs_info` immediately (no second call).
- Call 2: tool loop capped at ~6 steps; model picks tools; final answer is a typed `TripSuggestion` via structured output.
- Four mock tools, one per concern: `search_destinations`, `estimate_flights`, `find_hotels`, `compute_budget`.
- All arithmetic and hard constraints (budget totals, over/under, nightly caps, exclusions like "not Santorini") are enforced in Python, not by the prompt.
- Starting model: `claude-opus-4-8`. Smaller-model sweep is optional, only if time remains.

## D5. Two suites, kept separate
- `tests/` — fast, no API calls. Covers the D3 gate, budget math, tool mocks, schema parsing. Used to iterate on the loop.
- `evals/` — 5+ live cases against the real model. Used to judge final quality. Includes an LLM-as-judge dimension.

## D6. Eval scoring: three dimensions
1. **Structure** — response parses into the typed schema. Pass/fail. Deterministic.
2. **Behavior** — per-case Python checks (status, questions asked, budget respected, exclusions honored, tool calls made or skipped). Pass/fail per check.
3. **Fit** — LLM judge, `claude-opus-4-8` at low effort, scores 1–5 on vibe match and whether reasoning is grounded in tool results. Only subjective things go to the judge.
- Report: one row per case with the three scores, plus per-dimension averages.

## D7. Scope line and time plan
Must have (from the brief):
- Typed request/response (pydantic) with `ok` / `needs_info` statuses
- Gate + four mock tools + bounded loop, arithmetic in Python
- One-line CLI entry point
- `tests/` fast, no API calls
- `evals/` with six cases + summary report
- `README.md` runnable in under 5 minutes

Six eval cases, one thing each:
1. "Cheap." → must ask
2. Beach week, no headcount → must ask specifically for headcount
3. Beach week for two, $2000, JFK → must stay under budget
4. Europe long weekend from SFO → hotel under $300/night
5. Lisbon add-on → must skip the flight tool
6. Tokyo, $6k excluding flights → budget excludes flights, 8 nights

Optional, only after verification:
- Smaller-model sweep (Sonnet 5, then Haiku 4.5) on the same eval
- Anniversary case as a seventh eval
- Wider mock data

Time plan: ~55 min build, ~10 min live demo + eval run, last 25 min verification. If the eval run is slow, drop to five cases rather than cut verification.

## D8. Follow-ups from the spec review
- Total token spend for the whole project stays under $10. Eval runner prints usage and cost.
- "Long weekend" ⇒ 3 nights, "spring break" ⇒ 7 nights, assumed with a caveat.
- Headcount inference: "I'll be" / "I'm" ⇒ 1 adult; "we" / "anniversary" / "couple" ⇒ 2 adults. Always with a caveat.
- Still open: default daily spend for the budget tool (see SPEC.md §8 Q2).

## D9. Budget scope, guardrails, tracing
- Budget = flights + accommodation only. Food, activities, ground transport excluded from the initial scope and stated in a caveat. `compute_budget` has no daily-spend input.
- Basic guardrails in Python: input length check, user text kept out of the system prompt, 6-turn loop cap, pydantic validation of tool arguments, every dollar figure in the response re-checked against tool results, off-topic requests get `needs_info`, cost ledger with a $10 project cap.
- Tracing: one JSON trace per request under `traces/` (git-ignored) with input, extraction, gate decision, tool calls, model usage, and final output. CLI prints the trace path; eval report links each case to its trace.

## D10. Build plan
- Tasks, dependencies and parallel-agent dispatch are in `PLAN.md`: one lead on the critical path, four agents in wave 1 (models+gate, tools+data, tracing+guards, eval cases), two alongside in wave 2 (eval runner+judge, README).
- Agents own disjoint files and share stub signatures written in T0. Contract changes go through the lead.
