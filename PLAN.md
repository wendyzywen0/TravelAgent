# TravelAgent — Implementation plan

Companion to `SPEC.md`. Tasks, dependencies, and how work is split across parallel agents.
Time budget for build: ~50 minutes. Verification: last 25 minutes, untouchable.

## 1. Tasks

| ID | Task | Produces | Depends on | Owner |
|---|---|---|---|---|
| T0 | Scaffold + contracts | `pyproject.toml`, `uv sync`, package skeleton, key loading, **stub signatures** for models, gate, tools, tracer | — | lead |
| T1 | Models + gate | `models.py` (TripRequest/TripResponse/TripSuggestion), `gate.py` (D3 rules, headcount + trip-length inference), `tests/test_gate.py`, `tests/test_models.py` | T0 | agent A |
| T2 | Mock tools + data | `tools.py` (4 tools, pydantic arg schemas), `mock_data.py` (~12 destinations, fares, hotels), `tests/test_tools.py` | T0 | agent B |
| T3 | Tracing + guardrails | `trace.py` (JSON trace writer, request_id), `ledger.py` (cost ledger, $10 cap), `guards.py` (input checks, output cross-check vs tool results), `tests/test_guards.py` | T0 (contracts); cross-check uses T1/T2 shapes from the stubs | agent C |
| T4 | Agent loop | `agent.py`: call 1 extraction → gate → call 2 tool loop (cap 6) → final structured output → guards → trace | T1, T2, T3 | lead |
| T5 | CLI | `__main__.py`: one-line entry, `--verbose`, prints trace path | T4 | lead |
| T6a | Eval cases + checks | `evals/cases.py`: six cases, per-case Python behavior checks written against the T1 schema | T0 contracts (not T4) | agent D |
| T6b | Eval runner + judge + report | `evals/run.py`: runs cases, structure/behavior/fit scoring, judge prompt, table report, usage + cost, trace links | T6a, T4 (to run; can be written against the stub interface before T4 is done) | agent D |
| T7 | README | `README.md`: setup in <5 min, run/test/eval commands, design choices (tool split, orchestration, missing-info policy, eval dimensions, cuts) | T1, T2 for accuracy; final pass after T5/T6b | agent E |
| T8 | Live demo | one end-to-end request shown working, trace file opened | T5 | lead |
| T9 | Eval run + fixes | run `evals/run.py`, fix anything failing, re-run | T6b, T8 | lead |
| T10 | Verification | full `tests/`, full eval, README walkthrough from a fresh clone, secret scan, push | T9 | lead + user |

## 2. Dependency graph

```
T0 ──┬── T1 ──┐
     ├── T2 ──┼── T4 ── T5 ── T8 ──┐
     ├── T3 ──┘                     ├── T9 ── T10
     ├── T6a ── T6b ────────────────┘
     └── T7 (draft) ····· T7 (final pass after T5/T6b)
```

Critical path: T0 → T1/T2/T3 (parallel) → T4 → T5 → T8 → T9 → T10.
Everything off the critical path (T6a, T6b, T7) runs alongside it.

## 3. Agent dispatch

Agents are Claude Code subagents working in this repo on **disjoint files**. They share one
contract: the stub signatures written in T0. No agent changes a stub signature; if one needs
to, it reports back and the lead changes it.

Note: subagent work does not count against the $10 token budget in the spec. That budget is for
the TravelAgent app's own API calls (demo, evals, optional sweep).

### Wave 0 — lead, ~5 min, sequential
- T0. Write `pyproject.toml`, run `uv sync`, create the package, write the stubs:
  - `models.py`: class names and fields from SPEC §5.2, bodies may be `...`
  - `gate.py`: `def gate(req: TripRequest) -> list[str]` (missing fields)
  - `tools.py`: four function signatures + `TOOL_SPECS` list shape for the API
  - `trace.py`: `class Tracer` with `event(kind, **data)` and `write() -> Path`
  - `guards.py`: `check_input(text)`, `cross_check(resp, tool_results)`
- Commit the contract so every agent starts from the same tree.

### Wave 1 — 4 agents in parallel, ~15 min
| Agent | Task | Files owned | Done when |
|---|---|---|---|
| A | T1 | `models.py`, `gate.py`, `tests/test_gate.py`, `tests/test_models.py` | AC1, AC5 pass; the 7 sample inputs produce the expected missing-field lists |
| B | T2 | `tools.py`, `mock_data.py`, `tests/test_tools.py` | AC2, AC3, AC4 pass; mock data covers all six eval cases (JFK/SFO fares, Caribbean/Mexico beach, Europe walkable cities, near-Lisbon, Tokyo) |
| C | T3 | `trace.py`, `ledger.py`, `guards.py`, `tests/test_guards.py` | AC11, AC12, AC13 pass; a trace round-trips to JSON |
| D | T6a | `evals/cases.py` | six cases with behavior-check functions, each importable and unit-testable against hand-built `TripResponse` objects |

Each agent runs only its own test files. The lead runs the full suite after merging.

### Wave 2 — lead on critical path, 2 agents alongside, ~15 min
| Who | Task | Files owned |
|---|---|---|
| lead | T4, T5 | `agent.py`, `__main__.py`, `prompts.py` |
| D (continued) | T6b | `evals/run.py`, `evals/judge.py` |
| E | T7 draft | `README.md` |

### Wave 3 — lead, ~10 min
- T8 live demo on the beach-for-two input. Open the trace. Fix anything obvious.
- T9 run the eval. Fix failures. Re-run. E does the README final pass with real commands and real numbers.

### Wave 4 — last 25 min, lead + user
- T10 verification. No new features. Fresh-clone README walkthrough, full tests, full eval, secret scan, final push.

## 4. Integration rules

- One branch, `main`. Agents commit to their own files only; the lead merges by running the full test suite, not by reading every diff.
- If an agent is blocked on a contract change, it stops and reports rather than editing a file it does not own.
- Mock data is the most likely cross-agent mismatch (B's destination names vs D's eval expectations). Fix: B publishes the destination name list in `mock_data.py` first, within its first 3 minutes, and D reads from it.
- Any agent that finishes early runs its tests once more and stops. No scope additions.

## 5. Risks and cuts

| Risk | Cut if it bites |
|---|---|
| T4 structured output + tools in one loop is fiddly on `claude-opus-4-8` | Final answer via a single `strict` tool instead of `output_config.format`; same schema |
| Eval run is slow or expensive | Drop to five cases (remove case 4), keep verification time |
| Opus 4.8 is slow per call during demo | Lower effort to `low` for extraction, keep `medium` for the loop |
| An agent wanders outside its files | Lead reverts those files from the last commit and reassigns |
