"""Trip Idea agent: one natural-language request in, one typed suggestion out."""
from trip_agent.models import TripRequest, TripResponse, TripSuggestion

__all__ = ["TripRequest", "TripResponse", "TripSuggestion", "suggest_trip"]


def suggest_trip(text: str, client=None, trace_dir=None) -> TripResponse:  # thin re-export
    from trip_agent.agent import suggest_trip as _impl
    return _impl(text, client=client, trace_dir=trace_dir)
