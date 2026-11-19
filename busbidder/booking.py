"""Manage seat availability and saved bookings."""

from contextlib import closing
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
import logging
from pathlib import Path
import sqlite3
from uuid import uuid4

from .models import Offer


logger = logging.getLogger(__name__)
BOOKINGS_FILENAME = "bookings.sqlite3"


class BookingError(ValueError):
    """A booking could not be read or saved."""


@dataclass(frozen=True)
class Booking:
    """The journey and fare as they were when the traveller booked."""

    reference: str
    offer_id: str
    company: str
    destination: str
    departs_at: datetime
    arrives_at: datetime
    price_eur: Decimal
    changeable: bool
    refundable: bool
    booked_at: datetime


CREATE_BOOKINGS = """
CREATE TABLE IF NOT EXISTS bookings (
    reference TEXT PRIMARY KEY,
    offer_id TEXT NOT NULL,
    company TEXT NOT NULL,
    destination TEXT NOT NULL,
    departs_at TEXT NOT NULL,
    arrives_at TEXT NOT NULL,
    price_eur TEXT NOT NULL,
    changeable INTEGER NOT NULL,
    refundable INTEGER NOT NULL,
    booked_at TEXT NOT NULL
)
"""


class BookingStore:
    """Keep one record per booked seat, separate from the original offers."""

    def __init__(self, path: Path, offers: list[Offer]) -> None:
        self.path = path.resolve()
        # Keep the original seat counts. Search results show the seats left.
        self._offers = {offer.offer_id: offer for offer in offers}

    def available_offers(self) -> list[Offer]:
        """Return the offers with current seat counts, including sold-out trips."""
        try:
            self.path.stat()
        except FileNotFoundError:
            return list(self._offers.values())
        except OSError as error:
            logger.error("Could not read bookings: %s", error)
            raise BookingError(f"Could not read bookings at {self.path}.") from error

        try:
            with closing(sqlite3.connect(f"{self.path.as_uri()}?mode=ro", uri=True)) as db:
                # A new database can briefly exist before its first booking is saved.
                table = db.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'bookings'"
                ).fetchone()
                if table is None:
                    return list(self._offers.values())
                booked = dict(db.execute("SELECT offer_id, COUNT(*) FROM bookings GROUP BY offer_id"))
        except sqlite3.Error as error:
            logger.error("Could not read bookings: %s", error)
            raise BookingError(f"Could not read bookings at {self.path}.") from error

        return [
            replace(offer, seats_available=max(0, offer.seats_available - booked.get(offer.offer_id, 0)))
            for offer in self._offers.values()
        ]

    def confirm_booking(self, offer_id: str) -> Booking:
        """Check the latest seat count and save one booking if a seat is free."""
        if offer_id not in self._offers:
            raise BookingError(f"Unknown offer {offer_id}.")
        offer = self._offers[offer_id]
        if offer.seats_available < 1:
            raise BookingError(f"{offer_id} has no seats left.")

        try:
            with closing(sqlite3.connect(self.path)) as db, db:
                # Only one writer can recheck seats and save a booking at a time.
                db.execute("BEGIN IMMEDIATE")
                db.execute(CREATE_BOOKINGS)
                (booked_seats,) = db.execute(
                    "SELECT COUNT(*) FROM bookings WHERE offer_id = ?", (offer_id,)
                ).fetchone()
                if booked_seats >= offer.seats_available:
                    raise BookingError(f"{offer_id} has no seats left.")

                booking = Booking(
                    reference=f"BB-{uuid4().hex.upper()}",
                    offer_id=offer_id,
                    company=offer.company,
                    destination=offer.destination,
                    departs_at=offer.departs_at,
                    arrives_at=offer.arrives_at,
                    price_eur=offer.price_eur,
                    changeable=offer.changeable,
                    refundable=offer.refundable,
                    booked_at=datetime.now(timezone.utc),
                )
                db.execute(
                    """
                    INSERT INTO bookings (
                        reference, offer_id, company, destination, departs_at, arrives_at,
                        price_eur, changeable, refundable, booked_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        booking.reference, booking.offer_id, booking.company, booking.destination,
                        booking.departs_at.isoformat(), booking.arrives_at.isoformat(),
                        str(booking.price_eur), booking.changeable, booking.refundable,
                        booking.booked_at.isoformat(),
                    ),
                )
        except sqlite3.Error as error:
            logger.error("Could not save booking for %s: %s", offer_id, error)
            raise BookingError(f"Could not save a booking at {self.path}.") from error

        logger.info("Saved booking %s for %s", booking.reference, booking.offer_id)
        return booking
