"""Reproduce the rankings used in the project evaluation."""

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

from .filtering import filter_offers
from .models import Offer, TravelRequest
from .ranking import BudgetPrice, CRITERIA, RankedOffer, ScoreWeights, rank_offers


EXAMPLE_BUDGET = Decimal("50")
EXAMPLE_REQUEST = TravelRequest(
    "Malaga", date(2027, 7, 12), date(2027, 7, 14),
    max_price_eur=EXAMPLE_BUDGET, max_transfers=1, require_changeable=True,
)
DEPARTURE = "morning"
RESULT_COLUMNS = (
    "rank", "offer_id", "company", "fare_eur", "duration_minutes",
    *(f"{name}_score" for name in CRITERIA), "total",
)


def _result_row(row: RankedOffer) -> tuple[str | int, ...]:
    return (
        row.rank, row.offer.offer_id, row.offer.company, f"{row.offer.price_eur:.2f}",
        row.duration_minutes, *(f"{row.scores[name]:.1f}" for name in CRITERIA), f"{row.total:.1f}",
    )


def write_comparisons(
    offers: list[Offer], profiles: dict[str, ScoreWeights], output_dir: Path
) -> tuple[Path, Path]:
    """Save the profile and sensitivity comparisons using original CSV capacity."""
    eligible = filter_offers(offers, EXAMPLE_REQUEST).accepted
    without_o5 = [offer for offer in eligible if offer.offer_id != "O5"]
    if not without_o5 or len(without_o5) == len(eligible):
        raise ValueError("The comparison requires the Malaga example with O5 and other eligible offers.")
    output_dir.mkdir(parents=True, exist_ok=True)

    profile_path = output_dir / "profile_comparison.csv"
    with profile_path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target, lineterminator="\n")
        writer.writerow(("profile", *(f"{name}_weight" for name in CRITERIA), *RESULT_COLUMNS))
        for profile, weights in profiles.items():
            weight_values = weights.as_dict()
            for row in rank_offers(eligible, weights, DEPARTURE).offers:
                writer.writerow((profile, *(weight_values[name] for name in CRITERIA), *_result_row(row)))

    sensitivity_path = output_dir / "ranking_sensitivity.csv"
    with sensitivity_path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target, lineterminator="\n")
        writer.writerow(("price_method", "eligible_set", *RESULT_COLUMNS))
        # Hold the weights and the other scoring rules fixed in all four runs.
        for method, price_scale in (("min-max", None), ("budget", BudgetPrice(EXAMPLE_BUDGET))):
            for label, selected in (("all matches", eligible), ("without O5", without_o5)):
                ranked = rank_offers(selected, preferred_departure=DEPARTURE, price_scale=price_scale)
                for row in ranked.offers:
                    writer.writerow((method, label, *_result_row(row)))
    return profile_path, sensitivity_path
