"""Build the stage-by-stage loop review page from an eval results file and its traces.

Usage: uv run python -m evals.build_review [evals/results/<run>.json]  (default: newest results file)
Writes evals/review/loop-review.html.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
OUT = HERE / "review" / "loop-review.html"
TEMPLATE = HERE / "review" / "template.html"


def collect(results_path: Path) -> list[dict]:
    res = json.loads(results_path.read_text())
    out = []
    for c in res["results"]:
        t = json.loads(Path(c["trace_path"]).read_text())
        ev = t["events"]
        by = lambda k: [e for e in ev if e["kind"] == k]
        req = (by("extraction")[-1].get("request") if by("extraction") else {}) or {}
        req = {k: v for k, v in req.items() if v not in (None, [], False, "")}
        g = {k: v for k, v in (by("gate")[-1] if by("gate") else {}).items() if k not in ("kind", "t")}
        tools = [{k: e.get(k) for k in ("t", "name", "args", "result", "error", "duration_s", "raw_args") if k in e} for e in by("tool_call")]
        calls = [{k: e.get(k) for k in ("t", "purpose", "model", "input_tokens", "output_tokens", "duration_s") if k in e} for e in by("model_call")]
        ios = [{k: v for k, v in e.items() if k not in ("kind", "t")} for e in by("model_io")]
        fin = by("final")
        final = (fin[-1].get("response") if fin else None) or (fin[-1] if fin else None)
        if isinstance(final, dict):
            final = {k: v for k, v in final.items() if k not in ("request", "trace_path", "kind", "t")}
        out.append(dict(id=c["id"], name=c["name"], input=t["input"], expected=c["expected_status"],
                        structure=c["structure_pass"], behavior=f'{c["behavior_n"]}/{c["behavior_m"]}', failed=c["failed_checks"],
                        fit=c["fit"], rationale=c.get("fit_rationale"), judge_io=c.get("judge_io"),
                        extraction=req, gate=g, model_calls=calls, model_io=ios, tool_calls=tools, final=final,
                        errors=[{k: v for k, v in e.items() if k != "kind"} for e in by("error")],
                        totals=t.get("totals"), trace=Path(c["trace_path"]).name))
    return out


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted(RESULTS.glob("2*.json"))[-1]
    data = json.dumps(collect(path)).replace("</", "<\\/")
    OUT.write_text(TEMPLATE.read_text().replace("__DATA__", data))
    print(f"built {OUT} from {path.name}")


if __name__ == "__main__":
    main()
