"""Check saved fare terms, remaining seats and attempts to book the last seat."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import re
import sqlite3
from threading import Barrier

import pytest

from busbidder.booking import BookingError, BookingStore
from busbidder.data_loader import load_offers


@pytest.fixture
def single_seat_offer():
    data_dir = Path(__file__).resolve().parents[1] / "data"
    offer = next(offer for offer in load_offers(data_dir) if offer.offer_id == "O2")
    return replace(offer, seats_available=1)


def test_last_seat_and_fare_terms_are_saved(single_seat_offer, tmp_path):
    path = tmp_path / "bookings # test.sqlite3"
    store = BookingStore(path, [single_seat_offer])
    assert store.available_offers()[0].seats_available == 1
    assert not path.exists()

    booking = store.confirm_booking("O2")
    assert re.fullmatch(r"BB-[0-9A-F]{32}", booking.reference)
    assert booking.price_eur == single_seat_offer.price_eur
    assert booking.changeable and booking.refundable

    reopened = BookingStore(path, [single_seat_offer])
    assert reopened.available_offers()[0].seats_available == 0
    with pytest.raises(BookingError, match="O2 has no seats left"):
        reopened.confirm_booking("O2")

    with closing(sqlite3.connect(path)) as db:
        saved = db.execute(
            "SELECT reference, offer_id, company, destination, price_eur, changeable, refundable FROM bookings"
        ).fetchall()
    assert saved == [(booking.reference, "O2", "Camino Express", "Malaga", "46.00", 1, 1)]
    assert single_seat_offer.seats_available == 1


def test_can_book_two_seats_with_different_references(single_seat_offer, tmp_path):
    offer = replace(single_seat_offer, seats_available=2)
    other = replace(single_seat_offer, offer_id="O3", refundable=False)
    store = BookingStore(tmp_path / "bookings.sqlite3", [offer, other])

    first = store.confirm_booking("O2")
    assert [row.seats_available for row in store.available_offers()] == [1, 1]
    second = store.confirm_booking("O2")
    assert first.reference != second.reference
    assert [row.seats_available for row in store.available_offers()] == [0, 1]


def test_only_one_of_two_simultaneous_bookings_can_take_last_seat(single_seat_offer, tmp_path):
    path = tmp_path / "bookings.sqlite3"
    start = Barrier(2, timeout=5)

    def book():
        store = BookingStore(path, [single_seat_offer])
        start.wait()
        try:
            return store.confirm_booking("O2").reference
        except BookingError as error:
            assert str(error) == "O2 has no seats left."
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = [pool.submit(book) for _ in range(2)]
        references = [attempt.result(timeout=10) for attempt in attempts]
    assert sum(reference is not None for reference in references) == 1
    assert BookingStore(path, [single_seat_offer]).available_offers()[0].seats_available == 0


def test_unknown_or_sold_out_offer_cannot_create_booking_file(single_seat_offer, tmp_path):
    path = tmp_path / "bookings.sqlite3"
    store = BookingStore(path, [replace(single_seat_offer, seats_available=0)])
    with pytest.raises(BookingError, match="Unknown offer O99"):
        store.confirm_booking("O99")
    with pytest.raises(BookingError, match="O2 has no seats left"):
        store.confirm_booking("O2")
    assert not path.exists()


def test_unreadable_booking_data_does_not_show_stale_seats(single_seat_offer, tmp_path):
    path = tmp_path / "bookings.sqlite3"
    contents = b"This is not a SQLite database."
    path.write_bytes(contents)
    store = BookingStore(path, [single_seat_offer])
    with pytest.raises(BookingError, match="Could not read bookings"):
        store.available_offers()
    with pytest.raises(BookingError, match="Could not save a booking"):
        store.confirm_booking("O2")
    assert path.read_bytes() == contents
