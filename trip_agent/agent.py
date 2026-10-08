"""Orchestration: extract -> gate -> bounded tool loop -> guards -> trace. Owned by the lead / agent L."""
from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from typing import Any

import anthropic
from pydantic import BaseModel, ValidationError, create_model

from trip_agent import config, gate, guards, ledger, prompts, tools
from trip_agent.models import TripRequest, TripResponse, TripSuggestion
from trip_agent.trace import Tracer

EXTRACTION_MAX_TOKENS = 4000
LOOP_MAX_TOKENS = 8000
EXTRACTION_EFFORT = "low"
LOOP_EFFORT = "medium"
FINAL_TOOL = "final_answer"

LOOP_CAP_QUESTION = (
    "I couldn't finish planning this trip within my step limit. Could you simplify the request, "
    "for example one destination or region, one budget figure, and your dates or number of nights?"
)
LOOP_CAP_CAVEAT = "The planner stopped before producing a grounded answer, so no prices are shown."

TOOL_DESCRIPTIONS = {
    "search_destinations": "Find candidate destinations matching vibe keywords, season, and region, "
                           "never returning anything in exclusions. Returns name, country, region, "
                           "price_level (1-3), tags, typical_nightly_usd.",
    "estimate_flights": "Round-trip economy fare per person (USD) and flight hours between an origin airport "
                        "and a destination for a month. Returns an error when there is no data for the pair.",
    "find_hotels": "Hotels in a destination, filtered by style, nightly cap (USD), and must-have tags "
                   "such as 'pool'. Returns name, destination, nightly_usd, tags.",
    "compute_budget": "Exact trip total for flights plus hotel only: flight_per_person_usd * travelers "
                      "(when includes_flights) + nightly_usd * nights. Returns total_usd, breakdown, "
                      "fits and over_by_usd against user_budget_usd. Always use this instead of arithmetic.",
}
FINAL_DESCRIPTION = (
    "Submit the finished trip suggestion. Call exactly once, after all tool calls, with every dollar "
    "figure copied exactly from tool results."
)


# Structured outputs cap how many *optional* properties a schema may have, and every TripRequest field has a
# default. The extraction schema is the same model with every field required (nullable ones still accept
# null), so the model must state "unknown" explicitly instead of omitting it.
_REQUIRED_FIELDS: dict[str, Any] = {name: (f.annotation, ...) for name, f in TripRequest.model_fields.items()}
TripRequestExtraction: type[BaseModel] = create_model("TripRequestExtraction", **_REQUIRED_FIELDS)


class AgentError(RuntimeError):
    """The model stopped in a way the loop cannot recover from (max_tokens, refusal)."""


def build_tool_specs() -> list[dict[str, Any]]:
    """API tool definitions: the four mock tools (strict) plus final_answer.

    final_answer is not strict: strict mode forces additionalProperties=false on every object, which
    would make BudgetSummary.breakdown (a free-form dict) always empty. Pydantic validates it instead.
    """
    specs: list[dict[str, Any]] = []
    for name, (args_model, _fn) in tools.TOOLS.items():
        specs.append({
            "name": name,
            "description": TOOL_DESCRIPTIONS.get(name, name),
            "input_schema": _all_required(anthropic.transform_schema(args_model)),
            "strict": True,
        })
    specs.append({
        "name": FINAL_TOOL,
        "description": FINAL_DESCRIPTION,
        "input_schema": TripSuggestion.model_json_schema(),
    })
    return specs


def _all_required(schema: dict[str, Any]) -> dict[str, Any]:
    """Make every property required (nullable ones still accept null). An omitted field would otherwise
    fall back to a pydantic default, e.g. flight_per_person_usd=0.0, silently dropping a price."""
    schema = dict(schema)
    schema["required"] = list(schema.get("properties", {}))
    return schema


def suggest_trip(text: str, client=None, trace_dir: Path | None = None, verbose: bool = False) -> TripResponse:
    text = guards.check_input(text)
    tracer = Tracer(text, trace_dir, verbose)
    try:
        if client is None:
            client = anthropic.Anthropic(api_key=config.load_api_key())
        resp = _run(text, client, tracer)
    except Exception as exc:
        if not any(e.get("kind") == "error" for e in tracer.events):
            tracer.event("error", reason=type(exc).__name__, message=str(exc))
        exc.trace_path = str(tracer.write())  # type: ignore[attr-defined]  # read by the CLI
        _record_cost(tracer)
        raise
    tracer.event("final", response=resp.model_dump(mode="json", exclude={"trace_path"}))
    resp.trace_path = str(tracer.write())
    _record_cost(tracer)
    return resp


def _run(text: str, client: Any, tracer: Tracer) -> TripResponse:
    req = _extract(text, client, tracer)

    g = gate.gate(req)
    tracer.event("gate", ok=g.ok, missing=g.missing, assumptions=g.assumptions)
    gated = g.request or req
    if not g.ok:
        return TripResponse(status="needs_info", questions=g.questions, assumptions=g.assumptions, request=gated)

    suggestion = _tool_loop(gated, g.assumptions, client, tracer)
    if suggestion is None:
        return TripResponse(
            status="needs_info", questions=[LOOP_CAP_QUESTION],
            assumptions=[*g.assumptions, LOOP_CAP_CAVEAT], request=gated,
        )

    resp = TripResponse(status="ok", suggestion=suggestion, assumptions=g.assumptions, request=gated)
    try:
        guards.cross_check(resp, tracer.tool_calls())
    except guards.GuardError as exc:
        tracer.event("error", reason="cross_check", message=str(exc))
        raise
    tracer.event("cross_check", ok=True)
    return resp


def _extract(text: str, client: Any, tracer: Tracer) -> TripRequest:
    t0 = time.monotonic()
    msg = client.messages.parse(
        model=config.MODEL,
        max_tokens=EXTRACTION_MAX_TOKENS,
        system=prompts.EXTRACTION_SYSTEM,
        messages=[{"role": "user", "content": prompts.extraction_user_message(text, date.today())}],
        output_format=TripRequestExtraction,
        thinking={"type": "adaptive"},
        output_config={"effort": EXTRACTION_EFFORT},
    )
    _usage(tracer, msg, time.monotonic() - t0, f"extraction (effort={EXTRACTION_EFFORT})")
    parsed = msg.parsed_output
    _record_io(tracer, "extraction", prompts.EXTRACTION_SYSTEM,
               [{"role": "user", "content": prompts.extraction_user_message(text, date.today())}], msg,
               {"parsed": parsed.model_dump(mode="json") if parsed is not None else None})
    if parsed is None:
        tracer.event("error", reason="extraction", stop_reason=msg.stop_reason)
        raise AgentError(f"Extraction produced no TripRequest (stop_reason={msg.stop_reason}).")
    req = parsed if isinstance(parsed, TripRequest) else TripRequest.model_validate(parsed.model_dump())
    tracer.event("extraction", request=req)
    return req


def _tool_loop(req: TripRequest, assumptions: list[str], client: Any, tracer: Tracer) -> TripSuggestion | None:
    """Bounded manual loop. Returns the parsed final answer, or None if the model never produced one."""
    specs = build_tool_specs()
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompts.loop_user_message(req, assumptions)}]
    nudged = False

    for turn in range(1, config.MAX_LOOP_TURNS + 1):
        t0 = time.monotonic()
        msg = client.messages.create(
            model=config.MODEL,
            max_tokens=LOOP_MAX_TOKENS,
            system=prompts.LOOP_SYSTEM,
            messages=messages,
            tools=specs,
            thinking={"type": "adaptive"},
            output_config={"effort": LOOP_EFFORT},
        )
        _usage(tracer, msg, time.monotonic() - t0, f"loop turn {turn} (effort={LOOP_EFFORT})")
        _record_io(tracer, f"loop turn {turn}", prompts.LOOP_SYSTEM, [messages[-1]], msg,
                   {"tools": [t["name"] for t in specs]} if turn == 1 else None)
        messages.append({"role": "assistant", "content": msg.content})

        if msg.stop_reason in ("max_tokens", "refusal"):
            tracer.event("error", reason=msg.stop_reason, turn=turn)
            raise AgentError(f"Tool loop stopped with stop_reason={msg.stop_reason} on turn {turn}.")

        if msg.stop_reason == "tool_use":
            results, final = _dispatch(msg.content, tracer)
            if final is not None:
                return final
            if turn == config.MAX_LOOP_TURNS - 1:
                results.append({"type": "text", "text": prompts.LAST_TURN})
            messages.append({"role": "user", "content": results})
            continue

        if msg.stop_reason == "pause_turn":
            continue

        # end_turn / stop_sequence without a final_answer call: nudge once, then give up.
        if nudged:
            tracer.event("error", reason="no_final_answer", turn=turn)
            return None
        nudged = True
        messages.append({"role": "user", "content": prompts.NUDGE})

    tracer.event("error", reason="loop_cap", turns=config.MAX_LOOP_TURNS)
    return None


def _dispatch(content: list[Any], tracer: Tracer) -> tuple[list[dict[str, Any]], TripSuggestion | None]:
    """Run every tool_use block in a turn. Returns all tool_results (for one user message) and the final answer."""
    results: list[dict[str, Any]] = []
    final: TripSuggestion | None = None
    for block in content:
        if getattr(block, "type", None) != "tool_use":
            continue
        args = block.input if isinstance(block.input, dict) else {}
        if block.name == FINAL_TOOL:
            try:
                final = TripSuggestion.model_validate(args)
                tracer.event("final_answer", ok=True)
                results.append(_result(block.id, "Received."))
            except ValidationError as exc:
                tracer.event("final_answer", ok=False, error=str(exc))
                results.append(_result(block.id, f"Invalid final_answer: {exc}", error=True))
            continue
        results.append(_run_tool(block.id, block.name, args, tracer))
    return results, final


def _run_tool(tool_use_id: str, name: str, args: dict[str, Any], tracer: Tracer) -> dict[str, Any]:
    entry = tools.TOOLS.get(name)
    if entry is None:
        msg = f"Unknown tool '{name}'."
        tracer.event("tool_call", name=name, args=args, result=None, duration_s=0.0, error=msg)
        return _result(tool_use_id, msg, error=True)
    args_model, fn = entry
    try:
        parsed = args_model.model_validate(args)
    except ValidationError as exc:
        msg = f"Invalid arguments for {name}: {exc}"
        tracer.event("tool_call", name=name, args=args, result=None, duration_s=0.0, error=msg)
        return _result(tool_use_id, msg, error=True)

    trace_args: dict[str, Any] = {"args": parsed.model_dump(mode="json")}
    if trace_args["args"] != args:
        trace_args["raw_args"] = args

    t0 = time.monotonic()
    try:
        out = fn(parsed)
    except Exception as exc:  # a mock tool bug must not crash the loop
        msg = f"{name} failed: {type(exc).__name__}: {exc}"
        tracer.event("tool_call", name=name, **trace_args, result=None,
                     duration_s=round(time.monotonic() - t0, 4), error=msg)
        return _result(tool_use_id, msg, error=True)
    duration = round(time.monotonic() - t0, 4)

    if isinstance(out, tools.ToolError):
        tracer.event("tool_call", name=name, **trace_args, result=None, duration_s=duration, error=out.error)
        return _result(tool_use_id, json.dumps(out.model_dump(mode="json")), error=True)

    result = _dump(out)
    tracer.event("tool_call", name=name, **trace_args, result=result, duration_s=duration, error=None)
    return _result(tool_use_id, json.dumps(result))


def _dump(out: Any) -> Any:
    if isinstance(out, BaseModel):
        return out.model_dump(mode="json")
    if isinstance(out, list):
        return [_dump(o) for o in out]
    return out


def _result(tool_use_id: str, content: str, error: bool = False) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
    if error:
        block["is_error"] = True
    return block


def _blocks(content: Any) -> list[dict[str, Any]]:
    """Serialize response content blocks for the trace (thinking text is never returned by the API)."""
    out: list[dict[str, Any]] = []
    for b in content or []:
        t = getattr(b, "type", None)
        if t == "text":
            out.append({"type": "text", "text": getattr(b, "text", "")})
        elif t == "tool_use":
            out.append({"type": "tool_use", "name": getattr(b, "name", ""), "input": getattr(b, "input", {})})
        elif t in ("thinking", "redacted_thinking"):
            out.append({"type": "thinking", "omitted": True})
        else:
            out.append({"type": str(t)})
    return out


def _record_io(tracer: Tracer, purpose: str, system: str, sent: list[dict[str, Any]], msg: Any, extra: dict[str, Any] | None = None) -> None:
    """One model_io event per call: the system prompt, the NEW messages sent this call, and the raw response blocks."""
    tracer.event("model_io", purpose=purpose, system=system, sent=sent, stop_reason=getattr(msg, "stop_reason", None),
                 response=_blocks(getattr(msg, "content", None)), **(extra or {}))


def _usage(tracer: Tracer, msg: Any, duration_s: float, purpose: str) -> None:
    u = msg.usage
    tracer.add_usage(config.MODEL, int(u.input_tokens), int(u.output_tokens), round(duration_s, 3), purpose)


def _record_cost(tracer: Tracer) -> None:
    usage = getattr(tracer, "usage", [])
    tin = sum(int(u["input_tokens"]) for u in usage)
    tout = sum(int(u["output_tokens"]) for u in usage)
    cost = sum(ledger.estimate_cost_usd(u["model"], u["input_tokens"], u["output_tokens"]) for u in usage)
    if usage:
        ledger.record("suggest_trip", cost, tin, tout)
