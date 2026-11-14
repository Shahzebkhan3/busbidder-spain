"""Apply the traveller's mandatory requirements before ranking."""

from .models import Offer, TravelRequest


def rejection_reasons(offer: Offer, request: TravelRequest) -> list[str]:
    """Return each failed requirement. An empty list means the offer qualifies."""
    raise NotImplementedError("Milestone 3: implement the hard constraints.")
