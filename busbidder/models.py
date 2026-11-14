"""The information used to compare offers for a journey from Madrid."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class Offer:
    """One bus offer, including its price, ticket conditions and available seats.

    frozen=True prevents changes to the fields after an offer is created.
    The CSV loader checks the data. Creating an Offer directly does not check
    whether its values match the type hints or follow the validation rules.
    """

    offer_id: str
    company: str
    destination: str
    departs_at: datetime
    arrives_at: datetime
    price_eur: Decimal
    transfers: int
    changeable: bool
    refundable: bool
    seats_available: int


@dataclass(frozen=True)
class TravelRequest:
    """The traveller's requirements, ready for the filtering step.

    None means the traveller has not set that limit.
    When require_changeable is False, either type of ticket is allowed.
    """

    destination: str
    first_departure_date: date
    last_departure_date: date
    max_price_eur: Decimal | None = None
    max_transfers: int | None = None
    require_changeable: bool = False
