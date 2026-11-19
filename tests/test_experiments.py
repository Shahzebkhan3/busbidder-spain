"""Check the comparison claims and configuration errors."""

import csv
from decimal import Decimal
from pathlib import Path

import pytest

from busbidder.data_loader import InvalidRecordError, load_offers
from busbidder.experiments import write_comparisons
from busbidder.profiles import load_profiles
from busbidder.ranking import BudgetPrice


def test_only_relative_price_changes_winner_in_sensitivity_example(sample_data, tmp_path):
    offers = load_offers(sample_data)
    profiles = load_profiles(sample_data / "profiles.json")
    _, sensitivity = write_comparisons(offers, profiles, tmp_path / "results")
    with sensitivity.open(encoding="utf-8", newline="") as source:
        winners = {
            (row["price_method"], row["eligible_set"]): (row["offer_id"], row["total"])
            for row in csv.DictReader(source) if row["rank"] == "1"
        }
    assert winners == {
        ("min-max", "all matches"): ("O2", "60.0"),
        ("min-max", "without O5"): ("O3", "67.3"),
        ("budget", "all matches"): ("O2", "63.2"),
        ("budget", "without O5"): ("O2", "63.2"),
    }


def test_budget_scores_are_anchored_to_the_budget():
    scale = BudgetPrice(Decimal("50"))
    assert scale.score(Decimal("0")) == 100
    assert scale.score(Decimal("25")) == 50
    assert scale.score(Decimal("50")) == 0
    assert scale.score(Decimal("54")) == 0
    with pytest.raises(ValueError, match="positive budget"):
        BudgetPrice(Decimal("0"))


@pytest.mark.parametrize(
    "contents, error",
    [
        ('{"Budget": {"price": 100}', "invalid JSON"),
        ('{"Budget": {"price": 100}}', "needs weights"),
        ('{"Budget": {"price": true, "duration": 0, "departure": 0, "flexibility": 0}}', "must be numbers"),
        ('{"Budget": {"price": 90, "duration": 0, "departure": 0, "flexibility": 0}}', "add up to 100%"),
    ],
)
def test_invalid_profile_file_has_a_clear_error(tmp_path: Path, contents: str, error: str):
    config = tmp_path / "profiles.json"
    config.write_text(contents, encoding="utf-8")
    with pytest.raises(InvalidRecordError, match=error):
        load_profiles(config)
