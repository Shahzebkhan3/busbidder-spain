"""Check the traveller's requirements and the reasons offers are rejected."""

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
import logging

import pytest

from busbidder.data_loader import load_offers
from busbidder.filtering import filter_offers, rejection_reasons
from busbidder.models import InvalidRequestError, Offer, TravelRequest


@pytest.fixture
def request_details():
    return TravelRequest(
        destination="Malaga",
        first_departure_date=date(2027, 7, 12),
        last_departure_date=date(2027, 7, 14),
        max_price_eur=Decimal("50.00"),
        max_transfers=1,
        require_changeable=True,
    )


@pytest.fixture
def offer():
    return Offer(
        offer_id="O99", company="Camino Express", destination="Malaga",
        departs_at=datetime(2027, 7, 13, 9), arrives_at=datetime(2027, 7, 13, 14),
        price_eur=Decimal("46.00"), transfers=0,
        changeable=True, refundable=True, seats_available=10,
    )


def test_example_request_keeps_four_offers_and_explains_two_rejections(request_details, caplog, sample_data):
    offers = load_offers(sample_data)
    before = list(offers)
    with caplog.at_level(logging.INFO, logger="busbidder.filtering"):
        result = filter_offers(offers, request_details)
    assert [offer.offer_id for offer in result.accepted] == ["O2", "O3", "O4", "O5"]
    assert result.rejected == {
        "O1": ["Ticket must be changeable."],
        "O6": ["Price EUR 54.00 exceeds budget EUR 50.00."],
    }
    assert offers == before
    assert result.accepted[0] is offers[1]
    assert "Filtered 6 offers: 4 accepted, 2 rejected" in caplog.text


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("destination", "Barcelona", "Destination Barcelona does not match Malaga."),
        ("price_eur", Decimal("50.01"), "Price EUR 50.01 exceeds budget EUR 50.00."),
        ("transfers", 2, "2 transfers exceeds the limit of 1."),
        ("seats_available", 0, "No seats available."),
        ("changeable", False, "Ticket must be changeable."),
    ],
)
def test_each_failed_requirement_has_a_reason(offer, request_details, field, value, expected):
    assert rejection_reasons(replace(offer, **{field: value}), request_details) == [expected]


@pytest.mark.parametrize(
    "departure,arrival,matches",
    [
        (datetime(2027, 7, 11, 23, 59), datetime(2027, 7, 12, 5), False),
        (datetime(2027, 7, 12, 0, 0), datetime(2027, 7, 12, 5), True),
        (datetime(2027, 7, 14, 23, 59), datetime(2027, 7, 15, 5), True),
        (datetime(2027, 7, 15, 0, 0), datetime(2027, 7, 15, 5), False),
    ],
)
def test_departure_date_boundaries_and_overnight_arrival(
    offer, request_details, departure, arrival, matches
):
    reasons = rejection_reasons(replace(offer, departs_at=departure, arrives_at=arrival), request_details)
    assert (not reasons) is matches
    if not matches:
        assert len(reasons) == 1
        assert "outside 2027-07-12 to 2027-07-14" in reasons[0]


def test_exact_budget_transfer_limit_and_last_seat_are_accepted(offer, request_details):
    boundary_offer = replace(offer, price_eur=Decimal("50.00"), transfers=1, seats_available=1)
    assert rejection_reasons(boundary_offer, request_details) == []


def test_zero_budget_and_zero_transfers_are_real_limits(offer, request_details):
    request_details = replace(request_details, max_price_eur=Decimal("0"), max_transfers=0)
    assert rejection_reasons(replace(offer, price_eur=Decimal("0")), request_details) == []
    result = rejection_reasons(replace(offer, price_eur=Decimal("0.01"), transfers=1), request_details)
    assert len(result) == 2
    assert "budget EUR 0.00" in result[0]
    assert "limit of 0" in result[1]


def test_unspecified_limits_allow_expensive_and_nonchangeable_offers(offer, request_details):
    request_details = replace(request_details, max_price_eur=None, max_transfers=None, require_changeable=False)
    unrestricted = replace(offer, price_eur=Decimal("500"), transfers=5, changeable=False)
    assert rejection_reasons(unrestricted, request_details) == []
    assert rejection_reasons(replace(unrestricted, seats_available=0), request_details) == ["No seats available."]


def test_destination_matching_ignores_case_and_surrounding_spaces(offer, request_details):
    assert rejection_reasons(offer, replace(request_details, destination="  mALaGa  ")) == []


def test_all_reasons_are_returned_for_an_offer(offer, request_details):
    rejected = replace(
        offer, destination="Barcelona", price_eur=Decimal("60"), transfers=2,
        seats_available=0, changeable=False,
        departs_at=datetime(2027, 7, 15, 9), arrives_at=datetime(2027, 7, 15, 14),
    )
    reasons = rejection_reasons(rejected, request_details)
    assert len(reasons) == 6
    assert any("Destination" in reason for reason in reasons)
    assert any("Departure" in reason for reason in reasons)
    assert any("budget" in reason for reason in reasons)
    assert any("seats" in reason for reason in reasons)
    assert any("transfers" in reason for reason in reasons)
    assert any("changeable" in reason for reason in reasons)


def test_empty_input_returns_empty_results(request_details):
    result = filter_offers([], request_details)
    assert result.accepted == []
    assert result.rejected == {}


def test_no_matches_retains_all_rejection_reasons(offer, request_details):
    result = filter_offers([replace(offer, seats_available=0)], request_details)
    assert result.accepted == []
    assert result.rejected == {"O99": ["No seats available."]}


def test_single_offer_and_single_day_are_allowed(offer, request_details):
    request_details = replace(
        request_details, first_departure_date=date(2027, 7, 13), last_departure_date=date(2027, 7, 13)
    )
    result = filter_offers([offer], request_details)
    assert result.accepted == [offer]
    assert result.rejected == {}


@pytest.mark.parametrize(
    "field,value",
    [
        ("destination", " "),
        ("destination", None),
        ("first_departure_date", "2027-07-12"),
        ("first_departure_date", datetime(2027, 7, 12, 9)),
        ("last_departure_date", date(2027, 7, 11)),
        ("max_price_eur", Decimal("-0.01")),
        ("max_price_eur", Decimal("NaN")),
        ("max_price_eur", Decimal("Infinity")),
        ("max_price_eur", Decimal("50.001")),
        ("max_price_eur", 50.0),
        ("max_transfers", -1),
        ("max_transfers", 1.5),
        ("max_transfers", True),
        ("require_changeable", "false"),
    ],
)
def test_invalid_requests_are_rejected_when_created(request_details, field, value):
    with pytest.raises(InvalidRequestError):
        replace(request_details, **{field: value})
