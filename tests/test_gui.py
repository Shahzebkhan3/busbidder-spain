"""Check the search and booking flow through the Tkinter widgets."""

from dataclasses import replace
from pathlib import Path
import shutil
import sys

import pytest

tk = pytest.importorskip("tkinter")

from busbidder import __main__, gui
from busbidder.booking import BookingStore
from busbidder.data_loader import load_destinations, load_offers
from busbidder.profiles import CUSTOM_PROFILE, load_profiles


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tkinter could not open a window: {error}")
    root.withdraw()
    try:
        yield root
    finally:
        root.destroy()


@pytest.fixture
def window(tk_root, tmp_path, sample_data):
    # Reuse Tk, but give every test fresh widgets and its own booking file.
    offers = [
        replace(offer, seats_available=1) if offer.offer_id == "O2" else offer
        for offer in load_offers(sample_data)
    ]
    store = BookingStore(tmp_path / "bookings.sqlite3", offers)
    window = gui.SearchWindow(
        tk_root, store, sorted(load_destinations(sample_data)), offers,
        load_profiles(sample_data / "profiles.json"),
    )
    window.budget.set("50")
    window.transfers.set("1")
    window.changeable.set(True)
    window.departure.set("Morning")
    try:
        yield window
    finally:
        for widget in tk_root.winfo_children():
            widget.destroy()


def test_opening_without_search_arguments_launches_gui(monkeypatch, tmp_path):
    booking_path = tmp_path / "bookings.sqlite3"
    monkeypatch.setattr(sys, "argv", [
        "busbidder", "--data-dir", str(DATA_DIR), "--bookings-file", str(booking_path),
    ])
    monkeypatch.setattr(__main__, "__file__", str(tmp_path / "busbidder" / "__main__.py"))
    (tmp_path / "data").mkdir()
    shutil.copy2(DATA_DIR / "profiles.json", tmp_path / "data" / "profiles.json")
    calls = []

    def launch(bookings, destinations, offers, profiles):
        calls.append((bookings.path, destinations, offers, profiles))
        return 0

    monkeypatch.setattr(gui, "launch", launch)
    assert __main__.main() == 0
    assert len(calls) == 1
    used_path, destinations, offers, profiles = calls[0]
    assert used_path == booking_path.resolve()
    assert len(destinations) == 15
    assert len(offers) == 76
    assert "Budget traveller" in profiles


def test_search_shows_ranks_scores_and_rejection_reasons(window):
    window.search()
    assert window.tree.get_children() == ("O2", "O3", "O4", "O5")
    assert window.tree.set("O2", "score") == "60.0"
    assert "Camino Express (O2) ranks first" in window.recommendation.get()
    assert "Flexibility 100.0" in window.details.get()
    assert window.tabs.tab(1, "text") == "Rejected (2)"
    rejected = window.rejected_text.get("1.0", "end")
    assert "O1 · Ticket must be changeable." in rejected
    assert "O6 · Price EUR 54.00 exceeds budget EUR 50.00." in rejected


def test_changing_request_disables_old_booking_and_invalid_weights_are_reported(window):
    window.search()
    assert window.book_button.instate(["!disabled"])
    window.weights["price"].set("20")
    assert window.book_button.instate(["disabled"])
    assert "Search again" in window.status.get()
    window.search()
    assert "add up to 100%" in window.status.get()
    assert not window.tree.get_children()


def test_no_matches_leave_booking_disabled(window):
    window.budget.set("0")
    window.search()
    assert "No offers matched" in window.status.get()
    assert window.tabs.tab(1, "text") == "Rejected (6)"
    assert window.book_button.instate(["disabled"])


def test_profile_changes_weights_and_preserves_trip_requirements(window):
    window.search()
    window.profile.set("Budget traveller")
    window._apply_profile()
    assert window.profile.get() == "Budget traveller"
    assert window.weights["price"].get() == "85"
    assert window.budget.get() == "50"
    assert window.departure.get() == "Morning"
    assert window.book_button.instate(["disabled"])

    window.search()
    assert window.tree.get_children()[0] == "O5"
    window.weights["price"].set("80")
    assert window.profile.get() == CUSTOM_PROFILE


def test_booking_requires_confirmation_and_refreshes_after_last_seat(window, monkeypatch):
    receipts = []
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, message, **_: receipts.append(message))
    window.search()
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args, **kwargs: False)
    window.book_selected()
    assert not window.bookings.path.exists()
    assert receipts == []

    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args, **kwargs: True)
    window.book_selected()
    assert "Reference: BB-" in receipts[0]
    assert window.tree.get_children() == ("O3", "O5", "O4")
    assert "O2 · No seats available." in window.rejected_text.get("1.0", "end")
