"""The information used to compare offers for a journey from Madrid."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class Offer:
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
    destination: str
    first_departure_date: date
    last_departure_date: date
    max_price_eur: Decimal | None = None
    max_transfers: int | None = None
    require_changeable: bool = False
