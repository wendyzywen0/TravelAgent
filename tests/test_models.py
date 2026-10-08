"""AC5: TripResponse status/questions/suggestion consistency."""
import pytest
from pydantic import ValidationError

from trip_agent.models import DestinationPick, TripResponse, TripSuggestion


def suggestion() -> TripSuggestion:
    return TripSuggestion(
        destinations=[DestinationPick(name="Tulum", country="Mexico", why="beach")],
        reasoning="fits the budget",
    )


def test_needs_info_without_questions_fails():
    with pytest.raises(ValidationError):
        TripResponse(status="needs_info")


def test_needs_info_with_suggestion_fails():
    with pytest.raises(ValidationError):
        TripResponse(status="needs_info", questions=["How many?"], suggestion=suggestion())


def test_ok_without_suggestion_fails():
    with pytest.raises(ValidationError):
        TripResponse(status="ok")


def test_ok_with_questions_fails():
    with pytest.raises(ValidationError):
        TripResponse(status="ok", suggestion=suggestion(), questions=["How many?"])


def test_valid_both_ways():
    assert TripResponse(status="needs_info", questions=["How many?"]).suggestion is None
    assert TripResponse(status="ok", suggestion=suggestion()).questions == []
