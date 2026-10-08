"""Deterministic must-have check (SPEC §5.3). Owned by agent A."""
from __future__ import annotations
from dataclasses import dataclass, field
from trip_agent.models import TripRequest


@dataclass
class GateResult:
    missing: list[str] = field(default_factory=list)      # human-readable field names, e.g. "headcount"
    questions: list[str] = field(default_factory=list)    # one question per missing item, user-facing
    assumptions: list[str] = field(default_factory=list)  # e.g. "Assumed 2 adults (anniversary)"
    request: TripRequest | None = None                    # request with inferred defaults filled in

    @property
    def ok(self) -> bool:
        return not self.missing


def gate(req: TripRequest) -> GateResult:
    """Apply inference (solo/couple, long weekend, spring break, defaults) then the per-intent table."""
    raise NotImplementedError
