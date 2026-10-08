"""Settings and API-key loading. Nothing here talks to the network."""
from __future__ import annotations
import os
from pathlib import Path

MODEL = "claude-opus-4-8"
JUDGE_MODEL = "claude-opus-4-8"
MAX_LOOP_TURNS = 6
MAX_INPUT_CHARS = 2000
PROJECT_COST_CAP_USD = 10.0
PROJECT_ROOT = Path(__file__).resolve().parent.parent
KEY_FALLBACK = Path.home() / "tokens" / ".anthropic_api_key"
# USD per million tokens, used only for the cost ledger estimate.
PRICE_PER_MTOK = {"claude-opus-4-8": (5.0, 25.0), "claude-sonnet-5": (2.0, 10.0), "claude-haiku-4-5": (1.0, 5.0)}


def load_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key and KEY_FALLBACK.exists():
        key = KEY_FALLBACK.read_text().strip()
    if not key:
        raise RuntimeError("No API key. Set ANTHROPIC_API_KEY or put the key in ~/tokens/.anthropic_api_key")
    return key
