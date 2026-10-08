"""suggest_trip end to end with a scripted fake client. No network, no key."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from trip_agent import config
from trip_agent import prompts
from trip_agent.agent import LOOP_CAP_QUESTION, build_tool_specs, suggest_trip
from trip_agent.guards import GuardError
from trip_agent.models import TripRequest

Script = Callable[[int, list[dict[str, Any]]], SimpleNamespace]


# ---------- fake SDK objects ----------

def _usage(i: int = 100, o: int = 50) -> SimpleNamespace:
    return SimpleNamespace(input_tokens=i, output_tokens=o)


def tool_use(id_: str, name: str, inp: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=inp)


def text(t: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=t)


def turn(*blocks: SimpleNamespace, stop: str = "tool_use") -> SimpleNamespace:
    return SimpleNamespace(content=list(blocks), stop_reason=stop, usage=_usage())


class FakeMessages:
    def __init__(self, extracted: TripRequest, script: Script | None) -> None:
        self.extracted = extracted
        self.script = script
        self.parse_calls: list[dict[str, Any]] = []
        self.create_calls: list[dict[str, Any]] = []

    def parse(self, **kw: Any) -> SimpleNamespace:
        self.parse_calls.append(kw)
        return SimpleNamespace(parsed_output=self.extracted, stop_reason="end_turn", content=[], usage=_usage(80, 40))

    def create(self, **kw: Any) -> SimpleNamespace:
        snapshot = list(kw["messages"])  # the agent keeps appending to the same list
        self.create_calls.append({**kw, "messages": snapshot})
        assert self.script is not None, "tool loop should not have run"
        return self.script(len(self.create_calls), snapshot)


class FakeClient:
    def __init__(self, extracted: TripRequest, script: Script | None = None) -> None:
        self.messages = FakeMessages(extracted, script)


def tool_results(messages: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """tool_use_id -> {"content": parsed JSON or str, "is_error": bool} from the last user message."""
    last = messages[-1]
    assert last["role"] == "user" and isinstance(last["content"], list)
    out: dict[str, dict[str, Any]] = {}
    for b in last["content"]:
        assert b["type"] == "tool_result"
        try:
            content: Any = json.loads(b["content"])
        except json.JSONDecodeError:
            content = b["content"]
        out[b["tool_use_id"]] = {"content": content, "is_error": bool(b.get("is_error"))}
    return out


def read_trace(resp_path: str | None) -> dict[str, Any]:
    assert resp_path is not None
    p = Path(resp_path)
    assert p.exists()
    return json.loads(p.read_text())


@pytest.fixture(autouse=True)
def _isolate_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)  # ledger.LEDGER_PATH is relative; keep fake runs out of the real ledger


BEACH_FOR_TWO = TripRequest(
    intents=["destination", "accommodation", "budget"], origin_airport="JFK",
    vibe=["beach", "relaxing"], month_or_season="February", nights=7, travelers_adults=2,
    budget_total_usd=2000, hotel_style="nice", couple_signal=True,
)


# ---------- (a) "Cheap." -> needs_info, no second call ----------

def test_cheap_needs_info_without_tool_loop(tmp_path: Path) -> None:
    client = FakeClient(TripRequest(vibe=["cheap"]))
    resp = suggest_trip("Cheap.", client=client, trace_dir=tmp_path / "traces")

    assert resp.status == "needs_info"
    assert resp.suggestion is None and len(resp.questions) >= 3
    assert len(client.messages.parse_calls) == 1
    assert client.messages.create_calls == []

    call = client.messages.parse_calls[0]
    assert call["model"] == config.MODEL and call["output_format"].__name__ == "TripRequestExtraction"
    assert "Cheap." in call["messages"][0]["content"] and "Cheap." not in call["system"]

    trace = read_trace(resp.trace_path)
    assert Path(resp.trace_path or "").parent == tmp_path / "traces"
    gates = [e for e in trace["events"] if e["kind"] == "gate"]
    assert len(gates) == 1 and gates[0]["ok"] is False and "budget" in gates[0]["missing"]
    assert trace["totals"]["model_calls"] == 1
    assert (tmp_path / "cost_ledger.json").exists()


# ---------- (b) beach for two -> ok, grounded in real tool output ----------

def beach_script(step: int, messages: list[dict[str, Any]]) -> SimpleNamespace:
    if step == 1:
        return turn(
            text("Searching."),
            tool_use("t1", "search_destinations", {"vibe": ["beach"], "season": "February", "exclusions": []}),
            tool_use("t2", "estimate_flights", {"origin": "JFK", "destination": "Cancun", "month": "February"}),
            tool_use("t3", "compute_budget", {"travelers": 0, "nightly_usd": 100, "nights": 7}),  # invalid on purpose
        )
    if step == 2:
        r = tool_results(messages)
        assert not r["t1"]["is_error"] and any(c["name"] == "Cancun" for c in r["t1"]["content"])
        assert not r["t2"]["is_error"]
        assert r["t3"]["is_error"] and "travelers" in r["t3"]["content"]
        return turn(tool_use("t4", "find_hotels", {"destination": "Cancun", "style": "mid-upper",
                                                    "nightly_cap_usd": None, "must_haves": []}))
    if step == 3:
        # Flight fare comes from turn 1's result, hotel from turn 2's.
        flight = tool_results(messages[:-2])["t2"]["content"]
        hotels = tool_results(messages)["t4"]["content"]
        assert hotels, "find_hotels returned nothing for Cancun"
        h = hotels[0]
        return turn(tool_use("t5", "compute_budget", {
            "flight_per_person_usd": flight["round_trip_per_person_usd"], "travelers": 2,
            "nightly_usd": h["nightly_usd"], "nights": 7, "user_budget_usd": 2000, "includes_flights": True,
        }))
    if step == 4:
        flight = tool_results(messages[:-4])["t2"]["content"]
        h = tool_results(messages[:-2])["t4"]["content"][0]
        b = tool_results(messages)["t5"]["content"]
        return turn(tool_use("t6", "final_answer", {
            "destinations": [{
                "name": "Cancun", "country": "Mexico", "why": "Warm beaches in February, direct from JFK.",
                "hotel": {"name": h["name"], "nightly_usd": h["nightly_usd"], "tags": h["tags"]},
                "flight_estimate_usd": flight["round_trip_per_person_usd"],
                "estimated_total_usd": b["total_usd"],
            }],
            "reasoning": "Cancun fits the beach vibe and the budget per compute_budget.",
            "budget": {"total_usd": b["total_usd"], "user_budget_usd": 2000, "fits": b["fits"],
                       "over_by_usd": b["over_by_usd"], "breakdown": b["breakdown"],
                       "includes_flights": b["includes_flights"]},
            "caveats": ["Estimate covers flights and hotel only; food, activities, and ground transport "
                        "are not included."],
        }))
    raise AssertionError(f"unexpected turn {step}")


def test_beach_for_two_ok_and_grounded(tmp_path: Path) -> None:
    client = FakeClient(BEACH_FOR_TWO, beach_script)
    resp = suggest_trip("Relaxing beach week in February under $2000 for two, leaving from JFK. Want a nice hotel.",
                        client=client, trace_dir=tmp_path)

    assert resp.status == "ok" and resp.suggestion is not None
    assert len(client.messages.create_calls) == 4
    pick = resp.suggestion.destinations[0]
    assert pick.hotel is not None and pick.estimated_total_usd is not None
    assert resp.suggestion.budget is not None and resp.suggestion.budget.total_usd == pick.estimated_total_usd
    assert any("nice" in a.lower() for a in resp.assumptions)  # gate assumption passed through

    # Each turn's tool results went back in ONE user message, and the tool specs include final_answer.
    second = client.messages.create_calls[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]
    assert len(second[-1]["content"]) == 3
    names = {t["name"] for t in client.messages.create_calls[0]["tools"]}
    assert names == {"search_destinations", "estimate_flights", "find_hotels", "compute_budget", "final_answer"}

    trace = read_trace(resp.trace_path)
    calls = [e for e in trace["events"] if e["kind"] == "tool_call"]
    assert [c["name"] for c in calls] == ["search_destinations", "estimate_flights", "compute_budget",
                                          "find_hotels", "compute_budget"]
    assert calls[2]["error"] and calls[4]["error"] is None
    assert any(e["kind"] == "cross_check" and e["ok"] for e in trace["events"])
    assert trace["totals"]["model_calls"] == 5  # 1 extraction + 4 loop turns


def test_made_up_total_is_rejected(tmp_path: Path) -> None:
    def script(step: int, messages: list[dict[str, Any]]) -> SimpleNamespace:
        if step < 4:
            return beach_script(step, messages)
        out = beach_script(step, messages)
        out.content[0].input["destinations"][0]["estimated_total_usd"] = 1234.0
        return out

    with pytest.raises(GuardError) as exc:
        suggest_trip("Beach week for two in Feb under $2000 from JFK.", client=FakeClient(BEACH_FOR_TWO, script),
                     trace_dir=tmp_path)
    trace = read_trace(getattr(exc.value, "trace_path", None))
    assert any(e["kind"] == "error" and e.get("reason") == "cross_check" for e in trace["events"])


# ---------- (c) never calls final_answer -> loop cap ----------

def test_loop_cap_returns_needs_info(tmp_path: Path) -> None:
    def forever(step: int, messages: list[dict[str, Any]]) -> SimpleNamespace:
        return turn(tool_use(f"s{step}", "search_destinations", {"vibe": ["beach"]}))

    client = FakeClient(BEACH_FOR_TWO, forever)
    resp = suggest_trip("Beach week for two in Feb under $2000 from JFK.", client=client, trace_dir=tmp_path)

    assert resp.status == "needs_info" and resp.questions == [LOOP_CAP_QUESTION]
    assert len(client.messages.create_calls) == config.MAX_LOOP_TURNS
    assert any("stopped" in a for a in resp.assumptions)
    trace = read_trace(resp.trace_path)
    assert any(e["kind"] == "error" and e.get("reason") == "loop_cap" for e in trace["events"])
    # The model was warned before its last turn, in the same user message as the tool results.
    last_user = client.messages.create_calls[-1]["messages"][-1]["content"]
    assert last_user[-1] == {"type": "text", "text": prompts.LAST_TURN}


def test_strict_tool_schemas_require_every_argument() -> None:
    # An omitted argument would silently fall back to a pydantic default (e.g. a $0 flight).
    for spec in build_tool_specs():
        if spec.get("strict"):
            schema = spec["input_schema"]
            assert set(schema["required"]) == set(schema["properties"]), spec["name"]
            assert schema["additionalProperties"] is False


def test_end_turn_is_nudged_once_then_gives_up(tmp_path: Path) -> None:
    client = FakeClient(BEACH_FOR_TWO, lambda step, msgs: turn(text("Here you go!"), stop="end_turn"))
    resp = suggest_trip("Beach week for two in Feb under $2000 from JFK.", client=client, trace_dir=tmp_path)

    assert resp.status == "needs_info"
    assert len(client.messages.create_calls) == 2
    assert client.messages.create_calls[1]["messages"][-1] == {"role": "user", "content": "Call final_answer now."}
