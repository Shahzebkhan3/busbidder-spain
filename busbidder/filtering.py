"""Apply the traveller's mandatory requirements before ranking."""

from dataclasses import dataclass
import logging

from .models import Offer, TravelRequest


logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    """Matching offers and rejection reasons grouped by offer ID."""

    accepted: list[Offer]
    rejected: dict[str, list[str]]


def rejection_reasons(offer: Offer, request: TravelRequest) -> list[str]:
    """Check a validated offer. An empty list means it meets every requirement."""
    reasons = []
    # Ignore typing differences such as " malaga " versus "Malaga".
    if offer.destination.strip().casefold() != request.destination.strip().casefold():
        reasons.append(
            f"Destination {offer.destination} does not match {request.destination.strip()}."
        )

    # Only departure needs to fall within the requested dates. An overnight
    # bus may arrive the day after the end of the travel window.
    departure_date = offer.departs_at.date()
    if not request.first_departure_date <= departure_date <= request.last_departure_date:
        reasons.append(
            f"Departure {departure_date} is outside "
            f"{request.first_departure_date} to {request.last_departure_date}."
        )

    if request.max_price_eur is not None and offer.price_eur > request.max_price_eur:
        reasons.append(
            f"Price EUR {offer.price_eur:.2f} exceeds budget EUR {request.max_price_eur:.2f}."
        )
    if offer.seats_available < 1:
        reasons.append("No seats available.")
    if request.max_transfers is not None and offer.transfers > request.max_transfers:
        reasons.append(f"{offer.transfers} transfers exceeds the limit of {request.max_transfers}.")
    if request.require_changeable and not offer.changeable:
        reasons.append("Ticket must be changeable.")

    # Keep every reason so the user can see all the requirements an offer fails.
    return reasons


def filter_offers(offers: list[Offer], request: TravelRequest) -> FilterResult:
    """Filter loaded offers, preserving their order and leaving their data intact.

    The CSV loader checks offer values and unique IDs before this function runs.
    Matching offers are ready for the ranking step.
    """
    accepted = []
    rejected = {}
    for offer in offers:
        reasons = rejection_reasons(offer, request)
        if reasons:
            rejected[offer.offer_id] = reasons
        else:
            accepted.append(offer)

    logger.info("Filtered %d offers: %d accepted, %d rejected", len(offers), len(accepted), len(rejected))
    return FilterResult(accepted=accepted, rejected=rejected)
