"""CLI: uv run python -m trip_agent "beach week in February under $2000 for two from JFK" [--verbose] [--json]"""
from __future__ import annotations

import argparse
import logging
import sys

from trip_agent.agent import suggest_trip
from trip_agent.guards import GuardError


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="trip_agent", description="Suggest a trip from one sentence.")
    p.add_argument("text", help="Your travel request, in quotes.")
    p.add_argument("--verbose", action="store_true", help="Stream trace events to stderr as they happen.")
    p.add_argument("--json", action="store_true", help="Print only the response JSON (no summary line).")
    a = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(message)s")
    try:
        resp = suggest_trip(a.text, verbose=a.verbose)
    except GuardError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if getattr(exc, "trace_path", None):
            print(f"trace: {exc.trace_path}", file=sys.stderr)  # type: ignore[attr-defined]
        return 2

    print(resp.model_dump_json(indent=2))
    if not a.json:
        print(f"status: {resp.status}", file=sys.stderr)
    print(f"trace: {resp.trace_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
