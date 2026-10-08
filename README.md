# Trip Idea Agent

A single-turn agent: send it one travel request, get back one typed response. It either
returns a short, grounded trip suggestion (1-3 destinations, a hotel, a budget check) or asks
for whatever it's missing. It reasons with four mock tools — no real travel data, no real
prices. There is no conversation; if something is missing, you re-send a fuller prompt.

## Quick start

```bash
git clone <repo-url>
cd TravelAgent
uv sync
export ANTHROPIC_API_KEY=sk-ant-...
```

No key handy? The app also reads `~/tokens/.anthropic_api_key` if `ANTHROPIC_API_KEY` isn't set.

Run it:

```bash
uv run python -m trip_agent "Relaxing beach week in February under \$2000 for two, leaving from JFK. Want a nice hotel."
```

Run the fast tests (no API calls, no key needed):

```bash
uv run pytest
```

Run the live evals (calls the real model, costs a little money):

```bash
uv run python -m evals.run
```

Useful flags: `--cases` to run a subset, `--no-judge` to skip the LLM-judge dimension (faster,
free of judge cost, keeps Structure and Behavior). Add `--verbose` to any `trip_agent` run to
stream the trace to stderr as it happens. Every run prints its trace file path at the end;
traces are JSON files under `traces/` (git-ignored).

## Example output

What you'll see depends on what you type. Below are two shapes: one where the agent has to ask
for more, one where it has enough to answer. The lead replaces these placeholders with real
output after a live run.

<!-- REAL OUTPUT: needs_info -->
```json
{
  "status": "needs_info",
  "questions": [
    "What kind of trip are you after, and when? For example, a beach week in February or a city break in Europe this spring.",
    "Roughly what's your budget in US dollars, and should it cover flights?",
    "How many people are travelling (adults, plus any children and their ages)?",
    "Which airport will you be flying from?"
  ],
  "suggestion": null,
  "assumptions": [],
  "trace_path": "traces/20261008T213159433177_7cba9f91.json"
}
```
(Input: `"Cheap."` — nothing to go on, so the agent asks everything at once instead of guessing.)

<!-- REAL OUTPUT: ok -->
```json
{
  "status": "ok",
  "questions": [],
  "suggestion": {
    "destinations": [
      {
        "name": "Punta Cana",
        "country": "Dominican Republic",
        "why": "A warm, relaxing Caribbean beach escape that's ideal for a couple in February, with a beachfront mid-upper resort that keeps you comfortably under budget.",
        "hotel": {
          "name": "Punta Cana Breeze Resort",
          "nightly_usd": 150.0,
          "tags": [
            "pool",
            "mid-upper",
            "beachfront",
            "family"
          ]
        },
        "flight_estimate_usd": 420.0,
        "estimated_total_usd": 1890.0
      },
      {
        "name": "Cancun",
        "country": "Mexico",
        "why": "Classic February beach relaxation with a short 4-hour flight from JFK and a beachfront mid-upper resort, fitting right at your budget.",
        "hotel": {
          "name": "Riviera Maya Sands Resort",
          "nightly_usd": 175.0,
          "tags": [
            "pool",
            "mid-upper",
            "beachfront",
            "family"
          ]
        },
        "flight_estimate_usd": 380.0,
        "estimated_total_usd": 1985.0
      }
    ],
    "reasoning": "Both picks match your beach-and-relaxing vibe for a February couples trip and come in under the $2,000 budget including flights from JFK. Punta Cana is the top pick with the most budget margin ($1,890 total: $840 flights, $1,050 hotel). Cancun is a close second at $1,985. Both resorts are beachfront, mid-to-upper range, and have pools.",
    "budget": {
      "total_usd": 1890.0,
      "user_budget_usd": 2000.0,
      "fits": true,
      "over_by_usd": 0.0,
      "breakdown": {
        "flights": 840.0,
        "hotel": 1050.0
      },
      "includes_flights": true
    },
    "caveats": [
      "Estimate covers flights and hotel only; food, activities, and ground transport are not included.",
      "Assumed your budget includes flights.",
      "Read 'nice hotel' as mid-to-upper range.",
      "Hotel availability and exact rates vary; figures are estimates for February."
    ]
  },
  "assumptions": [
    "Assumed your budget includes flights.",
    "Read 'nice hotel' as mid-to-upper range."
  ]
}
```
(Input: the beach-week example above — all the fields the agent needs were already in the request.)

## How it works

```
text
  → [call 1] extract a typed request
  → [Python gate] check must-haves for the detected intent(s)
  → [bounded tool loop] model calls mock tools, up to 6 turns
  → [final_answer tool] model returns the typed suggestion
  → [Python cross-check] every dollar figure re-verified against tool output
  → [trace] one JSON file written under traces/
```

**Tool split.** Four tools, one job each: `search_destinations`, `estimate_flights`,
`find_hotels`, `compute_budget`. One job each makes each tool easy to mock and test on its own,
and the trace shows exactly which step backs up a claim. Budget math gets its own tool because
arithmetic should never come from the model — `compute_budget` is pure Python and the only
source of truth for totals; the model calls it instead of doing the math itself.

**Orchestration.** Gate, then a bounded loop — not a free-running agent and not a fixed
pipeline. A free loop (no cap) risks spinning or guessing when basic facts are missing. A fixed
pipeline (always call all four tools in order) wastes calls when, say, the user already has a
flight booked. The gate handles the cheap, deterministic question — do we even have enough to
proceed — in plain Python, fast and testable without touching the model. Only once it passes
does the model get a loop, and that loop is capped at 6 turns so it can't run forever.

**Missing-info policy.** What counts as "critical" depends on intent — destination search,
accommodation search, and budget planning each have their own must-have table (SPEC §5.3).
Anything missing from the relevant table is asked all at once, not one question at a time,
since this is single-turn. Softer gaps are inferred instead, with a caveat: no headcount signal
defaults to solo for "I" or couple for "we" (or anniversary/honeymoon), "long weekend" becomes 3
nights, "spring break" becomes 7 nights, and "nice" hotel becomes mid-upper price range.

**Guardrails.** Input over 2,000 characters (or empty) is rejected before any model call. The
user's text only ever goes into the user message, never the system prompt, so it can't rewrite
the agent's instructions. Tool arguments are pydantic-validated before a tool runs; bad
arguments come back as an error result, not a crash. The tool loop is capped at 6 turns. Every
dollar figure in the final answer is re-checked in Python against the actual tool results — a
number that doesn't trace back to a tool call fails the response instead of being shown. A cost
ledger stops new eval runs once the project passes $10 in total spend.

**Tracing.** Every request writes one JSON file to `traces/`: the raw input, the extracted
request, the gate decision, every tool call (arguments, result, duration), every model call
(model, tokens, duration), and the final response or error. The CLI prints the path at the end.

## Evals

Each of the six live cases is scored on three dimensions:

- **Structure** — does the response parse into the typed schema? Pass/fail.
- **Behavior** — per-case Python checks: right status, right questions, budget respected,
  exclusions honored, tools called or skipped as expected. Pass/fail per check.
- **Fit** — an Opus 4.8 judge, running at low thinking effort, scores 1-5 on two things only:
  does the suggestion match the vibe, and is the reasoning grounded in the tool results. Nothing
  Python can already check is handed to the judge.

| # | Case | What it checks |
|---|---|---|
| 1 | "Cheap." | Status is `needs_info`; questions cover budget, timing, headcount, origin |
| 2 | Beach week, Feb, under $2000, from JFK, no headcount given | `needs_info`; a question asks for headcount; no destinations returned |
| 3 | Beach week for two, under $2000, from JFK | `ok`; every total is ≤ $2000; budget fits; `compute_budget` was called |
| 4 | Long weekend in Europe from SFO, boutique under $300/night | `ok`; every hotel nightly rate ≤ $300; destination tagged Europe |
| 5 | Lisbon Oct 10-13 plus 5 days nearby, flight already booked | `ok`; `estimate_flights` never called; suggestion stays near Lisbon |
| 6 | Tokyo, 8 days in November, $6k excluding flights | `ok`; budget breakdown has no flight line; nights = 8; total ≤ $6000 |

<!-- REAL EVAL TABLE -->
Real run on 2026-10-08, `claude-opus-4-8` for agent and judge:

```text
id  name                                                     structure  behavior  fit  tokens in/out  trace
--  -------------------------------------------------------  ---------  --------  ---  -------------  ----------------------------------------------------------------------------
1   Cheap. (needs everything)                                pass       4/4       5    3817/329       traces/20261008T213723393123_c4151fc1.json
2   Beach week, no headcount                                 pass       2/2       4    3868/384       traces/20261008T213729651855_d7254078.json
3   Beach week for two, under $2000                          pass       3/3       5    28594/2888     traces/20261008T213804829966_99763211.json
4   Europe long weekend from SFO, boutique under $300/night  pass       2/2       5    28652/2721     traces/20261008T213837072802_b69dda95.json
5   Lisbon add-on, flight already booked                     pass       3/3       5    27571/2313     traces/20261008T213908035062_923b30ad.json
6   Tokyo, 8 days, $6k excluding flights                     pass       3/3       4    18179/1424     traces/20261008T213928767232_2072b131.json

Structure pass rate: 6/6 (100%)
Behavior pass rate (all checks): 6/6 (100%)
Mean fit: 4.67

Total tokens (agent + judge): 110681 in / 10059 out
Estimated cost (agent + judge): $0.8049
Project ledger total: $3.4835
```

*(Lead fills in actual scores and trace links per case after the real eval run.)*


## What the traces say about the loop

In every `ok` eval run the model used the same four loop turns: `search_destinations`, then
`estimate_flights` and `find_hotels` for each candidate, then `compute_budget` per candidate, then
`final_answer`. That is exactly the order a fixed pipeline would use. With four fixed tools the loop
is not making decisions; it is adding two to four model turns of latency and cost. The honest
production choice is a Python fan-out of all tool calls plus one model call to pick and explain,
keeping a bounded loop only for constraint relaxation (for example, a family budget that only fits at
5 nights instead of 7). The loop stays in this submission because the brief asks to see orchestration
choices defended; measuring both modes is tracked in issue #11.

## Future work (out of scope for the 2-hour build)

- #11 Agent loop vs fixed pipeline: measure both on the same eval, then pick.
- #12 Model comparison: find the smallest model that meets the quality bar.
- #13 Wider eval set: adversarial, ambiguous, and budget-relaxation cases.

## What was cut, and known limits

Cut per SPEC §4 (out of scope for this exercise): real travel data or any third-party travel
API, any UI beyond the CLI, multi-turn conversation or persistence, accounts or auth, and
deployment/caching/observability/retries. Budget only covers flights and hotel — food,
activities, and ground transport are explicitly out and called out as a caveat in the response.

Cut per D7, as optional and only worth doing if time remained: a smaller-model sweep (trying
Sonnet 5 or Haiku 4.5 instead of Opus 4.8), a seventh eval case (an anniversary trip), and wider
mock data beyond the sample inputs.

Known limits:
- Mock data only covers the sample inputs above — ask about a city not in the mock tables and
  you'll get a clear "no data" caveat, not a real answer.
- All prices are made up. Nothing here reflects real flights or hotel rates.
- Single turn only. The agent doesn't remember your last message; if it asks a question, put
  the answer in a new, fuller request.

## Project layout

```
trip_agent/
  __init__.py      # re-exports suggest_trip()
  __main__.py       # CLI entry point, --verbose, prints trace path
  agent.py          # orchestration: extract -> gate -> tool loop -> guards -> trace
  config.py         # model names, loop cap, API key loading
  gate.py           # must-have rules and inference (SPEC §5.3)
  guards.py         # input checks and the dollar-figure cross-check
  ledger.py         # cost ledger and the $10 project cap
  models.py         # TripRequest / TripResponse / TripSuggestion (pydantic)
  tools.py          # the four mock tools and their argument schemas
  mock_data.py      # hardcoded destinations, fares, hotels
  trace.py          # JSON trace writer

evals/
  __init__.py
  cases.py          # the six eval cases and their behavior checks
  run.py            # eval runner: structure/behavior/fit scoring, report
  judge.py          # the LLM-judge prompt and call

tests/
  conftest.py        # keeps tests key-free
  test_gate.py        # the seven sample inputs against the must-have table
  test_models.py      # schema validation (ok/needs_info consistency)
  test_tools.py        # mock tool behavior (exclusions, nightly cap, budget math)
  test_guards.py        # input limits and the dollar-figure cross-check
```
