# Handoff

State of the TravelAgent exercise at the end of the 2-hour window (2026-10-08). Read this first,
then `README.md` for how to run, `SPEC.md` for what was agreed, `DECISIONS.md` for why.

## Where things stand

- **All must-haves from the brief are delivered and pushed** to `main` on
  https://github.com/wendyzywen0/TravelAgent (private).
- **Tests:** 107 fast tests, no API key needed, under 2 seconds: `uv run pytest`.
- **Typecheck:** `uv run pyright` is clean.
- **Live eval:** 6 cases, structure 6/6, behavior 6/6, mean fit 4.67 on `claude-opus-4-8`.
  One run costs about $0.80 with the judge, $0.55 without. Project spend so far: about $4.50 of
  the $10 cap (see `cost_ledger.json`, git-ignored, created on first run).
- **Review page:** `evals/review/loop-review.html` shows every case stage by stage, including
  raw model prompts and responses. Rebuild with `uv run python -m evals.build_review`.

## Verify in 5 minutes

```bash
uv sync
uv run pytest
uv run python -m trip_agent "Cheap."
uv run python -m trip_agent "Tokyo for 8 days in November, two adults, \$6k budget excluding flights."
uv run python -m evals.run --no-judge
```

## What changed after the eval was first green

Three review findings were fixed late and are worth knowing about:

1. **Price laundering.** A made-up nightly price fed into `compute_budget` used to pass the
   cross-check. Now the budget tool's inputs must themselves come from tool results, each pick's
   hotel and fare are paired to its own destination, and the budget summary must match one
   `compute_budget` result field for field (`trip_agent/guards.py`).
2. **No fare data.** When `estimate_flights` has no data, the model used to pass a $0 fare. The
   budget tool now refuses that; the model prices hotel-only with the flight marked unknown. If the
   final answer still fails the cross-check, it is bounced back to the model once with the reason
   (one repair turn), and a second failure returns a customer-worded `needs_info` instead of an
   error (`trip_agent/agent.py`, `trip_agent/prompts.py`).
3. **Thin input.** "Cheap." was being treated as off-topic. The extraction prompt now treats thin
   travel-ish input as a request to clarify.

## Open work, in suggested order

All tracked as GitHub issues with the `future-work` label.

| Issue | What | Why first |
|---|---|---|
| #14 | Verify affordability claims and hotel names in prose (`reasoning`, `caveats`), not just structured fields | A real quality bug: case 6 praised an $850/night hotel as "under budget" when 8 nights is $6,800 against $6,000. Nothing caught it. Also fixes the boilerplate caveat that says "flights and hotel" when flights are excluded. |
| #11 | Agent loop vs fixed pipeline: measure both | Traces show the loop always makes the same 4 turns a pipeline would; a pipeline is 2 model calls instead of up to 7. Decide with numbers. |
| #12 | Model comparison | Everything runs on Opus 4.8. `evals/run.py --model` exists; sweep Sonnet 5 and Haiku 4.5 with the judge fixed on Opus. |
| #13 | Wider eval set | Six cases is one per sample input. Add adversarial, ambiguous, and no-data cases. |

Two smaller things noticed but not ticketed:
- When flights cannot be priced, the budget summary still says `fits: true` against a hotel-only
  total. The caveat explains it, but `fits` should probably be null in that case.
- Dollar figures in free text are not cross-checked (that is #14).

## Gotchas

- `traces/`, `evals/results/`, `cost_ledger.json` are git-ignored and anchored to the project
  root, so they are the same files no matter where you run from.
- The ledger blocks new eval runs at $10 total. Delete `cost_ledger.json` to reset it.
- Thinking is adaptive on Opus 4.8; the API never returns thinking text, so traces show thinking
  blocks as "omitted".
- `tests/test_agent_fake.py` scripts the model turn by turn with a fake client. If you change the
  loop's message shape, that file is where it shows.
- Publishing the review page as a Claude artifact drops a copy named `TravelAgent Loop Review.html`
  in the repo root; it is git-ignored.

## Decisions you might want to revisit

- Must-have table per intent (`DECISIONS.md` D3, D8): origin is only required when a total budget
  includes flights; a nightly cap alone does not ask for origin.
- Headcount inference: "I'll be" means 1, "we"/"anniversary" means 2, always stated as an assumption.
- Budget covers flights plus hotel only (D9). Food and activities are out by choice.
