"""LLM-as-judge: the Fit dimension (SPEC §7.2, D6.3). Owned by agent D.

Python already checks structure (schema) and behavior (per-case facts). The judge is for the
one thing Python can't check: does this *feel* like a good answer to what the user actually
asked, and is the reasoning grounded in the tool results rather than invented.
"""
from __future__ import annotations

import json
import time
from typing import Any

import anthropic
from pydantic import BaseModel, Field

from trip_agent import config
from trip_agent.models import TripResponse

from evals.cases import EvalCase

JUDGE_SYSTEM = (
    "You are grading one response from a trip-planning assistant against the traveler's "
    "original request.\n\n"
    "Score ONLY two things:\n"
    "(a) Vibe/constraint match - do the picks (or, for a clarifying-questions response, the "
    "questions) actually fit what the user expressed (mood, season, region, must-haves, "
    "exclusions)?\n"
    "(b) Groundedness - is the reasoning built on the tool results you were shown, not invented "
    "facts, prices, or places?\n\n"
    "Do NOT grade budget arithmetic, schema/field correctness, or whether the response chose to "
    "ask questions versus give a suggestion - all of that is already checked separately and is "
    "out of scope for your score.\n\n"
    "If the response asked clarifying questions (status 'needs_info'), judge whether those "
    "specific questions are the right ones for what's actually missing from the request - not "
    "whether asking was the right call in the first place.\n\n"
    "Score 1 (way off - wrong vibe, or reasoning not supported by the tool results) to "
    "5 (excellent match, fully grounded). Give a short, specific rationale."
)


class JudgeScore(BaseModel):
    score: int = Field(ge=1, le=5)
    rationale: str


def _compact_tool_results(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only what the judge needs per call: name, args, result, error. Drops trace bookkeeping (t, duration_s).

    `error` is kept so failed calls (e.g. "no fare data for ...") are visible, not just a null result.
    """
    compact: list[dict[str, Any]] = []
    for call in tool_calls:
        item: dict[str, Any] = {
            "name": call.get("name"),
            "args": call.get("args"),
            "result": call.get("result"),
        }
        if call.get("error"):
            item["error"] = call.get("error")
        compact.append(item)
    return compact


def _build_user_message(case: EvalCase, resp: TripResponse, tool_calls: list[dict[str, Any]]) -> str:
    tool_results_json = json.dumps(_compact_tool_results(tool_calls), default=str, indent=2)
    response_json = resp.model_dump_json(indent=2, exclude={"trace_path"})
    return (
        f"Original request from the user:\n{case.input}\n\n"
        f"Tool results the assistant had available (in call order):\n{tool_results_json}\n\n"
        f"Final response:\n{response_json}\n"
    )


def judge(
    case: EvalCase,
    resp: TripResponse,
    tool_calls: list[dict[str, Any]],
    client: Any = None,
    usage_out: dict[str, Any] | None = None,
) -> JudgeScore:
    """Score Fit for one eval case's result.

    Accepts an injectable client for testing. If `usage_out` is given, it is filled in-place
    with this call's usage record ({model, input_tokens, output_tokens, duration_s, purpose}) -
    `evals/run.py` passes a dict here so it can fold judge usage into the project's cost ledger
    without changing this function's return type.
    """
    if client is None:
        client = anthropic.Anthropic(api_key=config.load_api_key())

    t0 = time.monotonic()
    message = client.messages.parse(
        model=config.JUDGE_MODEL,
        max_tokens=1500,
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": _build_user_message(case, resp, tool_calls)}],
        thinking={"type": "adaptive"},
        output_config={"effort": "low"},
        output_format=JudgeScore,
    )
    duration_s = time.monotonic() - t0

    if usage_out is not None:
        usage = getattr(message, "usage", None)
        usage_out.update({
            "model": config.JUDGE_MODEL,
            "input_tokens": getattr(usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(usage, "output_tokens", 0) or 0,
            "duration_s": duration_s,
            "purpose": f"judge case {case.id}",
        })

    score = message.parsed_output
    if score is None:
        raise RuntimeError(f"Judge produced no JudgeScore (stop_reason={message.stop_reason}).")
    return score
