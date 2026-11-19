"""Check the scoring rules against the worked example and edge cases."""

from dataclasses import replace
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from busbidder.data_loader import load_offers
from busbidder.filtering import filter_offers
from busbidder.models import TravelRequest
from busbidder.ranking import ScoreWeights, departure_score, rank_offers


@pytest.fixture
def sample_offers():
    data_dir = Path(__file__).resolve().parents[1] / "data"
    request = TravelRequest(
        "Malaga", date(2027, 7, 12), date(2027, 7, 14), Decimal("50"), 1, True,
    )
    return filter_offers(load_offers(data_dir), request).accepted


def test_worked_example_scores_and_explanation(sample_offers):
    result = rank_offers(sample_offers, preferred_departure="morning")
    assert [(row.offer.offer_id, row.total) for row in result.offers] == [
        ("O2", Decimal("60.0")), ("O3", Decimal("52.7")),
        ("O4", Decimal("50.4")), ("O5", Decimal("50.0")),
    ]
    winner, *_, overnight = result.offers
    assert winner.scores == {"price": 0, "duration": 100, "departure": 100, "flexibility": 100}
    assert overnight.duration_minutes == 480
    assert overnight.scores == {"price": 100, "duration": 0, "departure": 0, "flexibility": 50}
    assert "gains most on flexibility (+10.00 weighted points)" in result.recommendation
    assert "price (-9.60 weighted points)" in result.recommendation


def test_removing_nochevia_changes_the_minmax_winner(sample_offers):
    remaining = [offer for offer in sample_offers if offer.offer_id != "O5"]
    result = rank_offers(remaining, preferred_departure="morning")
    assert [(row.offer.offer_id, row.total) for row in result.offers] == [
        ("O3", Decimal("67.3")), ("O2", Decimal("60.0")), ("O4", Decimal("58.3")),
    ]


@pytest.mark.parametrize(
    "preference,clock_time,expected",
    [
        ("morning", time(1, 0), "16.7"),
        ("morning", time(6, 0), "100.0"),
        ("morning", time(12, 0), "100.0"),
        ("morning", time(13, 0), "83.3"),
        ("morning", time(15, 0), "50.0"),
        ("morning", time(18, 0), "0.0"),
        ("afternoon", time(15, 0), "100.0"),
        ("evening", time(23, 30), "100.0"),
        ("evening", time(0, 0), "100.0"),
        ("evening", time(1, 0), "83.3"),
        ("any", time(2, 0), "50.0"),
    ],
)
def test_departure_periods_and_distance_across_midnight(preference, clock_time, expected):
    score = departure_score(clock_time, preference)
    assert round(score, 1) == Decimal(expected)


def test_any_time_adds_the_same_departure_points_to_every_offer(sample_offers):
    result = rank_offers(sample_offers)
    assert {row.scores["departure"] for row in result.offers} == {Decimal("50")}
    assert "Any time was selected." in result.notes[-1]
    assert result.offers[0].total == Decimal("57.5")


def test_changing_weights_changes_the_top_offer(sample_offers):
    price_first = ScoreWeights(price=Decimal("85"), duration=Decimal("5"), departure=Decimal("5"), flexibility=Decimal("5"))
    result = rank_offers(sample_offers, price_first, "morning")
    assert result.offers[0].offer.offer_id == "O5"
    assert result.offers[0].total == Decimal("87.5")


def test_no_matches_produce_no_recommendation():
    result = rank_offers([])
    assert result.offers == []
    assert result.recommendation is None


def test_single_offer_has_neutral_minmax_scores_and_a_clear_message(sample_offers):
    result = rank_offers([sample_offers[0]], preferred_departure="morning")
    (row,) = result.offers
    assert row.scores == {"price": 50, "duration": 50, "departure": 100, "flexibility": 100}
    assert row.total == Decimal("67.5")
    assert "only offer matching your requirements" in result.recommendation
    assert len(result.notes) == 2


def test_identical_price_and_duration_are_neutral_for_multiple_offers(sample_offers):
    qualified = sample_offers[0]
    other = replace(qualified, offer_id="O9", refundable=False)
    result = rank_offers([qualified, other], preferred_departure="morning")
    assert [row.total for row in result.offers] == [Decimal("67.5"), Decimal("57.5")]
    assert all(row.scores["price"] == row.scores["duration"] == 50 for row in result.offers)


def test_different_totals_that_display_the_same_score_share_rank(sample_offers):
    base = sample_offers[0]
    cheap = replace(base, offer_id="O7", price_eur=Decimal("20"))
    also_cheap = replace(cheap, offer_id="O3")
    expensive = replace(base, offer_id="O6", price_eur=Decimal("50"))
    less_flexible = replace(base, offer_id="O8", refundable=False)
    weights = ScoreWeights(Decimal("0.02"), Decimal("0"), Decimal("0"), Decimal("99.98"))
    result = rank_offers([expensive, cheap, less_flexible, also_cheap], weights)
    assert [(row.offer.offer_id, row.rank, row.tied, row.total) for row in result.offers] == [
        ("O3", 1, True, Decimal("100.0")), ("O7", 1, True, Decimal("100.0")),
        ("O6", 1, True, Decimal("100.0")), ("O8", 4, False, Decimal("50.0")),
    ]
    assert "O3, O7, O6 share first place" in result.recommendation


def test_total_exactly_halfway_rounds_up_even_with_repeating_scores(sample_offers):
    base = sample_offers[0]
    intermediate = replace(
        base, offer_id="O7", price_eur=Decimal("44"), changeable=False, refundable=False,
        arrives_at=base.departs_at + timedelta(minutes=311),
    )
    cheap_and_long = replace(
        base, offer_id="O8", price_eur=Decimal("40"),
        arrives_at=base.departs_at + timedelta(minutes=312),
    )
    weights = ScoreWeights(Decimal("25"), Decimal("17"), Decimal("0"), Decimal("58"))
    result = rank_offers([base, intermediate, cheap_and_long], weights)
    row = next(row for row in result.offers if row.offer.offer_id == "O7")
    # 25 × (2/6) + 17 × (1/12) = 9.75, exactly halfway between 9.7 and 9.8.
    assert row.total == Decimal("9.8")


@pytest.mark.parametrize(
    "weights",
    [
        ("39", "25", "15", "20"),
        ("-1", "66", "15", "20"),
        ("101", "0", "0", "0"),
        ("NaN", "25", "15", "20"),
        ("Infinity", "25", "15", "20"),
        ("40.001", "24.999", "15", "20"),
    ],
)
def test_invalid_weights_are_rejected(weights):
    with pytest.raises(ValueError, match="weight"):
        ScoreWeights(*(Decimal(value) for value in weights))
