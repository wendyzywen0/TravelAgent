"""Eval runner: drives the six live cases through `suggest_trip` and scores three
dimensions - Structure, Behavior, Fit (SPEC §7.2, D6). Owned by agent D.

    uv run python -m evals.run [--cases 1,3] [--no-judge] [--model MODEL]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trip_agent import config, ledger
from trip_agent.agent import suggest_trip
from trip_agent.models import TripResponse

from evals.cases import CASES, EvalCase, load_tool_calls
from evals.judge import judge as judge_fn

RESULTS_DIR = Path("evals/results")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the TravelAgent live eval suite.")
    parser.add_argument("--cases", type=str, default=None, help="Comma-separated case ids to run, e.g. 1,3")
    parser.add_argument("--no-judge", action="store_true", help="Skip the Fit (LLM judge) dimension")
    parser.add_argument("--model", type=str, default=None, help="Override the agent's model for this run")
    return parser.parse_args(argv)


def _select_cases(ids: str | None) -> list[EvalCase]:
    if not ids:
        return list(CASES)
    wanted = {int(x) for x in ids.split(",") if x.strip()}
    return [c for c in CASES if c.id in wanted]


def _trace_usage(trace_path: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(Path(trace_path).read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return list(data.get("usage", []))


def _usage_cost(usage_records: list[dict[str, Any]]) -> tuple[int, int, float]:
    tokens_in = sum(int(u.get("input_tokens", 0)) for u in usage_records)
    tokens_out = sum(int(u.get("output_tokens", 0)) for u in usage_records)
    cost = sum(
        ledger.estimate_cost_usd(
            u.get("model", config.MODEL), int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0))
        )
        for u in usage_records
    )
    return tokens_in, tokens_out, cost


def run_case(case: EvalCase, run_judge: bool) -> dict[str, Any]:
    """Run one eval case end to end. Never raises - failures are recorded in the result dict."""
    result: dict[str, Any] = {
        "id": case.id,
        "name": case.name,
        "expected_status": case.expected_status,
        "structure_pass": False,
        "behavior_pass": None,
        "behavior_n": 0,
        "behavior_m": len(case.checks),
        "failed_checks": [],
        "fit": None,
        "trace_path": None,
        "usage": [],
        "error": None,
    }

    try:
        resp = suggest_trip(case.input)
    except Exception as exc:  # structure fail; record the error and move on
        result["error"] = f"{type(exc).__name__}: {exc}"
        trace_path = getattr(exc, "trace_path", None)
        if trace_path:
            result["trace_path"] = trace_path
            result["usage"] = _trace_usage(trace_path)
        return result

    result["trace_path"] = resp.trace_path
    tool_calls = load_tool_calls(resp.trace_path) if resp.trace_path else []
    if resp.trace_path:
        result["usage"] = _trace_usage(resp.trace_path)

    result["structure_pass"] = isinstance(resp, TripResponse) and resp.status == case.expected_status

    n_pass = 0
    for label, fn in case.checks:
        try:
            ok = bool(fn(resp, tool_calls))
        except Exception as exc:  # a check raising counts as a failed check, not a crashed run
            ok = False
            result["failed_checks"].append(f"{label} (error: {exc})")
            continue
        if ok:
            n_pass += 1
        else:
            result["failed_checks"].append(label)
    result["behavior_n"] = n_pass
    result["behavior_pass"] = n_pass == len(case.checks)

    if run_judge:
        try:
            judge_usage: dict[str, Any] = {}
            score = judge_fn(case, resp, tool_calls, usage_out=judge_usage)
            result["fit"] = score.score
            result["fit_rationale"] = score.rationale
            if judge_usage:
                result["usage"].append(judge_usage)
        except Exception as exc:
            result["fit_error"] = f"{type(exc).__name__}: {exc}"

    return result


def _fmt_fit(result: dict[str, Any]) -> str:
    return str(result["fit"]) if result["fit"] is not None else "-"


def _print_table(results: list[dict[str, Any]]) -> None:
    headers = ["id", "name", "structure", "behavior", "fit", "tokens in/out", "trace"]
    rows: list[list[str]] = []
    for r in results:
        structure = "pass" if r["structure_pass"] else "FAIL"
        behavior = f"{r['behavior_n']}/{r['behavior_m']}"
        tin, tout, _ = _usage_cost(r["usage"])
        rows.append([
            str(r["id"]), r["name"], structure, behavior, _fmt_fit(r), f"{tin}/{tout}",
            r["trace_path"] or "-",
        ])

    widths = [
        max(len(h), *(len(row[i]) for row in rows)) if rows else len(h)
        for i, h in enumerate(headers)
    ]

    def fmt_row(cells: list[str]) -> str:
        return "  ".join(c.ljust(w) for c, w in zip(cells, widths))

    print(fmt_row(headers))
    print(fmt_row(["-" * w for w in widths]))
    for row, r in zip(rows, results):
        print(fmt_row(row))
        if r["failed_checks"]:
            print(f"    failed: {', '.join(r['failed_checks'])}")
        if r.get("error"):
            print(f"    error: {r['error']}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        ledger.check_cap()
    except RuntimeError as exc:
        print(f"Eval run blocked by the cost ledger: {exc}", file=sys.stderr)
        return 1

    cases = _select_cases(args.cases)
    if not cases:
        print("No matching cases.", file=sys.stderr)
        return 1

    original_model = config.MODEL
    if args.model:
        config.MODEL = args.model
    try:
        results = [run_case(case, run_judge=not args.no_judge) for case in cases]
    finally:
        config.MODEL = original_model

    _print_table(results)

    n = len(results)
    structure_passes = sum(1 for r in results if r["structure_pass"])
    behavior_passes = sum(1 for r in results if r["behavior_pass"])
    fits = [r["fit"] for r in results if r["fit"] is not None]
    mean_fit = sum(fits) / len(fits) if fits else None

    print()
    print(f"Structure pass rate: {structure_passes}/{n} ({structure_passes / n:.0%})")
    print(f"Behavior pass rate (all checks): {behavior_passes}/{n} ({behavior_passes / n:.0%})")
    print(f"Mean fit: {mean_fit:.2f}" if mean_fit is not None else "Mean fit: - (judge skipped)")

    all_usage = [u for r in results for u in r["usage"]]
    total_in, total_out, total_cost = _usage_cost(all_usage)
    print()
    print(f"Total tokens: {total_in} in / {total_out} out")
    print(f"Estimated cost: ${total_cost:.4f}")

    cumulative = ledger.record("eval", total_cost, total_in, total_out)
    print(f"Project ledger total: ${cumulative:.4f}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    out_path = RESULTS_DIR / f"{stamp}.json"
    out_path.write_text(json.dumps({
        "model": args.model or config.MODEL,
        "judge_model": config.JUDGE_MODEL,
        "ran_judge": not args.no_judge,
        "results": results,
        "summary": {
            "structure_pass_rate": structure_passes / n,
            "behavior_pass_rate": behavior_passes / n,
            "mean_fit": mean_fit,
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "estimated_cost_usd": total_cost,
            "ledger_total_usd": cumulative,
        },
    }, indent=2, default=str))
    print(f"Wrote {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
