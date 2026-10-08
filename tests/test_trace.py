from __future__ import annotations

import json

from trip_agent.trace import Tracer


def test_trace_round_trips_to_json(tmp_path):
    tracer = Tracer("beach week for two", trace_dir=tmp_path)
    tracer.event("gate", missing=[], assumptions=["Assumed 2 adults."])
    tracer.event(
        "tool_call",
        name="find_hotels",
        args={"destination": "Lisbon"},
        result=[{"name": "Hotel A", "nightly_usd": 120.0, "tags": ["pool"]}],
        duration_s=0.01,
    )
    tracer.add_usage("claude-opus-4-8", input_tokens=100, output_tokens=50, duration_s=1.2, purpose="extraction")
    tracer.event("final", status="ok")

    path = tracer.write()
    assert path.exists()
    assert path.parent == tmp_path

    data = json.loads(path.read_text())
    for key in ("request_id", "input", "started_at", "events", "usage", "totals"):
        assert key in data

    assert data["request_id"] == tracer.request_id
    assert data["input"] == "beach week for two"
    assert isinstance(data["started_at"], str)


def test_tool_calls_returns_only_tool_call_events(tmp_path):
    tracer = Tracer("some trip", trace_dir=tmp_path)
    tracer.event("extraction", request={"intents": []})
    tracer.event("tool_call", name="search_destinations", args={}, result=[], duration_s=0.01)
    tracer.event("tool_call", name="compute_budget", args={}, result={"total_usd": 500.0}, duration_s=0.02)
    tracer.event("final", status="ok")

    calls = tracer.tool_calls()
    assert len(calls) == 2
    assert all(c["kind"] == "tool_call" for c in calls)
    assert [c["name"] for c in calls] == ["search_destinations", "compute_budget"]


def test_totals_are_summed_correctly(tmp_path):
    tracer = Tracer("another trip", trace_dir=tmp_path)
    tracer.event("tool_call", name="find_hotels", args={}, result=[], duration_s=0.01)
    tracer.event("tool_call", name="estimate_flights", args={}, result={}, duration_s=0.01)
    tracer.add_usage("claude-opus-4-8", input_tokens=200, output_tokens=80, duration_s=1.0, purpose="extraction")
    tracer.add_usage("claude-opus-4-8", input_tokens=300, output_tokens=120, duration_s=2.0, purpose="final")

    path = tracer.write()
    data = json.loads(path.read_text())

    assert data["totals"]["input_tokens"] == 500
    assert data["totals"]["output_tokens"] == 200
    assert data["totals"]["model_calls"] == 2
    assert data["totals"]["tool_calls"] == 2


def test_request_id_is_eight_hex_chars(tmp_path):
    tracer = Tracer("x", trace_dir=tmp_path)
    assert len(tracer.request_id) == 8
    int(tracer.request_id, 16)  # raises if not hex


def test_write_defaults_to_traces_dir_name():
    # No call to write() here, so nothing actually touches disk.
    tracer = Tracer("x")
    assert str(tracer.trace_dir) == "traces"
