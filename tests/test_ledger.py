from __future__ import annotations

import json

import pytest

from trip_agent import config, ledger


def test_estimate_cost_usd_known_model():
    in_rate, out_rate = config.PRICE_PER_MTOK["claude-opus-4-8"]
    cost = ledger.estimate_cost_usd("claude-opus-4-8", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == pytest.approx(in_rate + out_rate)


def test_estimate_cost_usd_unknown_model_uses_opus_rate():
    opus_cost = ledger.estimate_cost_usd("claude-opus-4-8", input_tokens=10_000, output_tokens=5_000)
    unknown_cost = ledger.estimate_cost_usd("some-future-model", input_tokens=10_000, output_tokens=5_000)
    assert unknown_cost == pytest.approx(opus_cost)


def test_record_accumulates(tmp_path):
    path = tmp_path / "cost_ledger.json"

    total1 = ledger.record("run1", cost_usd=1.0, input_tokens=100, output_tokens=50, path=path)
    assert total1 == pytest.approx(1.0)

    total2 = ledger.record("run2", cost_usd=2.5, input_tokens=200, output_tokens=75, path=path)
    assert total2 == pytest.approx(3.5)

    data = json.loads(path.read_text())
    assert len(data["runs"]) == 2
    assert data["total_usd"] == pytest.approx(3.5)
    for run in data["runs"]:
        assert set(run.keys()) == {"run_label", "cost_usd", "input_tokens", "output_tokens", "at"}


def test_check_cap_fine_when_file_missing(tmp_path):
    path = tmp_path / "missing_ledger.json"
    ledger.check_cap(path=path)  # should not raise


def test_check_cap_raises_at_or_over_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_COST_CAP_USD", 5.0)
    path = tmp_path / "cost_ledger.json"

    ledger.record("run1", cost_usd=4.0, input_tokens=100, output_tokens=50, path=path)
    ledger.check_cap(path=path)  # under cap, should not raise

    ledger.record("run2", cost_usd=1.0, input_tokens=100, output_tokens=50, path=path)
    with pytest.raises(RuntimeError):
        ledger.check_cap(path=path)  # exactly at cap


def test_check_cap_raises_over_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_COST_CAP_USD", 5.0)
    path = tmp_path / "cost_ledger.json"

    ledger.record("run1", cost_usd=6.0, input_tokens=100, output_tokens=50, path=path)
    with pytest.raises(RuntimeError):
        ledger.check_cap(path=path)
