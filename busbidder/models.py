"""The information used to compare offers for a journey from Madrid."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


class InvalidRequestError(ValueError):
    """The traveller has entered an invalid search requirement."""

    pass


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
    """The traveller's requirements, checked when the request is created.

    None means the traveller has not set that limit.
    When require_changeable is False, either type of ticket is allowed.
    Both dates are included in the departure window.
    """

    destination: str
    first_departure_date: date
    last_departure_date: date
    max_price_eur: Decimal | None = None
    max_transfers: int | None = None
    require_changeable: bool = False

    def __post_init__(self) -> None:
        """Catch invalid requests before any offers are filtered."""
        if not isinstance(self.destination, str) or not self.destination.strip():
            raise InvalidRequestError("Enter a destination.")
        # datetime also counts as a date in Python. Require dates here so a
        # hidden time of day cannot change the travel window.
        if type(self.first_departure_date) is not date or type(self.last_departure_date) is not date:
            raise InvalidRequestError("The travel window must contain two dates.")
        if self.first_departure_date > self.last_departure_date:
            raise InvalidRequestError("The last departure date must be on or after the first.")

        if self.max_price_eur is not None:
            if not isinstance(self.max_price_eur, Decimal):
                raise InvalidRequestError("The budget must be a Decimal value.")
            if not self.max_price_eur.is_finite() or self.max_price_eur < 0:
                raise InvalidRequestError("The budget must be a finite number of zero or more.")
            if self.max_price_eur.as_tuple().exponent < -2:
                raise InvalidRequestError("The budget must have at most two decimal places.")

        if self.max_transfers is not None:
            if type(self.max_transfers) is not int or self.max_transfers < 0:
                raise InvalidRequestError("The transfer limit must be a whole number of zero or more.")
        if type(self.require_changeable) is not bool:
            raise InvalidRequestError("The changeable-ticket requirement must be true or false.")
