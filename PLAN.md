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

## 6. Tickets (vertical slices) and how they map to the waves

The waves above are a horizontal cut by layer, chosen for parallelism. The GitHub tickets are
vertical slices, each demoable on its own. Parent issue #1 holds the spec; #2–#10 are sub-issues
with native blocked-by edges.

| Ticket | Slice | Blocked by | Maps to |
|---|---|---|---|
| #2 | "Cheap." end to end: scaffold, models, gate, extraction, trace, CLI | — | T0 + T1 + trace half of T3 + thin T4/T5 |
| #3 | Beach-for-two end to end: four tools, bounded loop, price cross-check | #2 | T2 + guards half of T3 + full T4 |
| #4 | Eval harness: three dimensions, judge, report, cost ledger | #3 | T6a + T6b |
| #5 | Ask for headcount and origin (eval case 2) | #4 | gate rules, fan-out |
| #6 | Europe long weekend from SFO, nightly cap (eval case 4) | #4 | mock data + fan-out |
| #7 | Lisbon add-on, skip flights, solo inference (eval case 5) | #4 | mock data + fan-out |
| #8 | Tokyo excluding flights, exclusions honored (eval case 6) | #4 | mock data + fan-out |
| #9 | Guardrails: input limits, off-topic, injection, loop-cap fallback | #3 | rest of T3 |
| #10 | README and fresh-clone walkthrough | #4, #9 | T7 |

Frontier after #4 lands: #5, #6, #7, #8, #9 can all run in parallel. #6, #7, #8 each touch mock
data, so the agents working them must add rows, never rewrite the table.

---

# Phase 2 — web interface with clarification rounds

Decisions: `DECISIONS.md` W1–W4. The agent stays single-turn; the web layer owns the rounds.

## 1. Shape

```
browser (one static page)  ──HTTP/JSON──▶  FastAPI server  ──in-process──▶  suggest_trip(merged_text)
                                               │
                                               ├─ session store: dict + web_sessions/<id>.json
                                               └─ background thread per run, polled by the page
```

One run = build the merged text from the session, call the agent, store the `TripResponse`.
If the response is `needs_info`, the page shows one box per question plus "anything else";
the answers become the next round and the whole history is re-sent.

## 2. Merged text (W1, W4)

```
Original request:
<text as typed>

Clarifications (later answers override earlier statements if they conflict):
Round 1
Q: How many people are travelling (adults, plus any children and their ages)?
A: Two adults
Anything else: we'd like a pool

Round 2
Q: Which airport will you be flying from?
A: JFK
```

Rules: empty answers are omitted; rounds are numbered in order; the full question text is kept so
the agent sees what was asked; the result must stay under the agent's 2,000-char limit or the
server returns 400 before calling the agent.

## 3. API contract

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST` | `/api/sessions` | `{"text": str}` | `{"session_id"}`; starts run 1 |
| `GET` | `/api/sessions/{id}` | — | full session state (below) |
| `POST` | `/api/sessions/{id}/answers` | `{"answers": [{"question": str, "answer": str}], "extra": str}` | `202` and starts the next run; `409` if a run is in flight or the round cap is reached; `400` if the merged text is too long |
| `GET` | `/api/sessions/{id}/trace` | — | the latest run's trace JSON |
| `DELETE` | `/api/sessions/{id}` | — | removes the session and its file |
| `GET` | `/` | — | the page |

Session state:

```json
{
  "session_id": "…",
  "original_text": "…",
  "rounds": [{"answers": [{"question": "…", "answer": "…"}], "extra": "…"}],
  "merged_text": "…",
  "status": "running" | "done" | "error",
  "response": <TripResponse> | null,
  "error": str | null,
  "trace_path": str | null,
  "run_count": 2,
  "rounds_left": 1,
  "started_at": "…", "finished_at": "…"
}
```

## 4. Files

| File | Purpose |
|---|---|
| `web/__init__.py` | package |
| `web/merge.py` | pure function `merge(original, rounds) -> str`; the only place the prompt shape lives |
| `web/store.py` | `Session` dataclass, in-memory dict, JSON load/save under `web_sessions/`, id generation |
| `web/app.py` | FastAPI routes, background run thread, timeout, round cap, error mapping |
| `web/__main__.py` | `uv run python -m web` → uvicorn on 127.0.0.1:8000 |
| `web/static/index.html` | the page: request box, status with elapsed time, rounds history, question form, result cards, trace link, start over |
| `tests/test_merge.py` | merge shape, empty answers dropped, ordering, length check |
| `tests/test_web.py` | TestClient with `web.app.suggest_trip` monkeypatched: needs_info → answers → ok; round cap → 409; too long → 400; concurrent run → 409; trace endpoint |
| `pyproject.toml` | `web` dependency group (fastapi, uvicorn, httpx for TestClient) in `default-groups` |
| `README.md` | "Web UI" section: one command, what the page does, the round cap |
| `.gitignore` | `web_sessions/` |

No change to `trip_agent/` is expected. If one is needed, it is a contract change and goes through the lead.

## 5. Tasks and dependencies

| ID | Task | Depends on | Owner |
|---|---|---|---|
| P0 | Add `web` dependency group, `web/` skeleton, `.gitignore`, the API contract as stubs | — | lead |
| P1 | `merge.py` + `tests/test_merge.py` | P0 | agent |
| P2 | `store.py` + `app.py` + `tests/test_web.py` (fake agent) | P0, P1 | lead |
| P3 | `index.html` against the API contract | P0 (contract only) | agent, parallel with P1/P2 |
| P4 | Live end-to-end in the browser: "beach week, no headcount" → answer "two" → `ok`; "Cheap." → 4 questions → answers → `ok` | P2, P3 | lead |
| P5 | README web section; eval case 7 (two-round) optional | P4 | agent |

```
P0 ──┬── P1 ── P2 ──┐
     └── P3 ────────┴── P4 ── P5
```

Estimated effort: about 90 minutes of build with two agents in parallel, plus two live runs
(about $0.40).

## 6. Tests that must pass before commit

- Merge: given original + two rounds, the text has the exact shape in §2; empty answers are
  dropped; a merged text over 2,000 chars is rejected with a clear message.
- Server (fake agent): create → `running` → `done` with `needs_info`; post answers → merged text
  contains the Q/A lines → `done` with `ok`; third round after cap → `409`; post while running →
  `409`; unknown id → `404`; delete removes the file.
- Existing 107 tests unchanged.

## 7. Ambiguities to discuss (recorded in DECISIONS.md W4)

1. Session expiry and listing: none planned.
2. Round cap value (3) and what happens at the cap: stop and offer "start over" vs the agent's graceful wording.
3. Progress: polling vs streaming trace events.
4. Timeout (120 s) with no kill switch; see #15.
5. Whether the 2,000-char input limit should be higher for web use.
6. Whether the page should let the user edit the original request, not just append rounds.
7. Whether a two-round case belongs in the eval suite.
