"""Score eligible offers for the traveller's chosen preferences."""

from collections import Counter
from dataclasses import dataclass
from datetime import time
from decimal import Decimal
from fractions import Fraction

from .models import Offer


DEPARTURE_WINDOWS = {
    "morning": (6 * 60, 12 * 60),
    "afternoon": (12 * 60, 18 * 60),
    "evening": (18 * 60, 24 * 60),
}
DEPARTURE_CHOICES = ("any", *DEPARTURE_WINDOWS)
CRITERIA = ("price", "duration", "departure", "flexibility")
NEUTRAL_SCORE = Fraction(50)


@dataclass(frozen=True)
class ScoreWeights:
    """The four percentages entered by the traveller, adding up to 100."""

    price: Decimal = Decimal("40")
    duration: Decimal = Decimal("25")
    departure: Decimal = Decimal("15")
    flexibility: Decimal = Decimal("20")

    def as_dict(self) -> dict[str, Decimal]:
        return {
            "price": self.price,
            "duration": self.duration,
            "departure": self.departure,
            "flexibility": self.flexibility,
        }

    def __post_init__(self) -> None:
        weights = self.as_dict()
        for name, weight in weights.items():
            if not isinstance(weight, Decimal) or not weight.is_finite() or not 0 <= weight <= 100:
                raise ValueError(f"The {name} weight must be a percentage from 0 to 100.")
            if weight.as_tuple().exponent < -2:
                raise ValueError(f"The {name} weight must have at most two decimal places.")
        if sum(weights.values()) != 100:
            raise ValueError("The four weights must add up to 100%.")


@dataclass
class RankedOffer:
    """An offer with its scores and shared rank for display."""

    offer: Offer
    duration_minutes: int
    scores: dict[str, Decimal]
    total: Decimal
    rank: int = 0
    tied: bool = False


@dataclass
class RankingResult:
    """The sorted offers, scoring notes and recommendation for a search."""

    offers: list[RankedOffer]
    notes: list[str]
    recommendation: str | None


def lower_is_better(value: Decimal, minimum: Decimal, maximum: Decimal) -> Fraction:
    """Give the lowest eligible value 100 and the highest 0."""
    if minimum == maximum:
        return NEUTRAL_SCORE
    # Keep the ratio exact so values like 1/3 don't affect rounding later.
    low, high = Fraction(minimum), Fraction(maximum)
    return 100 * (high - Fraction(value)) / (high - low)


def departure_score(departure: time, preference: str) -> Fraction:
    """Score the distance to the chosen time window, including across midnight."""
    if preference == "any":
        return NEUTRAL_SCORE
    if preference not in DEPARTURE_WINDOWS:
        raise ValueError(f"Choose a departure preference from {', '.join(DEPARTURE_CHOICES)}.")

    start, end = DEPARTURE_WINDOWS[preference]
    minute = departure.hour * 60 + departure.minute
    if start <= minute <= end:
        return Fraction(100)
    # Check both directions around the clock to find the closer edge.
    minutes_per_day = 24 * 60
    minutes_away = min((start - minute) % minutes_per_day, (minute - end) % minutes_per_day)
    return Fraction(max(0, 360 - minutes_away) * 100, 360)


def _recommendation(offers: list[RankedOffer], weights: dict[str, Decimal]) -> str:
    top = offers[0]
    if len(offers) == 1:
        return f"{top.offer.company} ({top.offer.offer_id}) is the only offer matching your requirements."

    if top.tied:
        first_ids = [row.offer.offer_id for row in offers if row.rank == 1]
        return (
            f"{', '.join(first_ids)} share first place at {top.total:.1f} under these weights. "
            "Tied offers are listed by price, then by offer ID."
        )

    runner_up = offers[1]
    differences = {
        name: (top.scores[name] - runner_up.scores[name]) * weights[name] / 100
        for name in CRITERIA
    }
    advantage = max(differences, key=differences.__getitem__)
    disadvantage = min(differences, key=differences.__getitem__)
    text = (
        f"{top.offer.company} ({top.offer.offer_id}) ranks first under these weights. "
        f"Compared with {runner_up.offer.company} ({runner_up.offer.offer_id}), "
        f"it gains most on {advantage} (+{differences[advantage]:.2f} weighted points)."
    )
    if differences[disadvantage] < 0:
        text += f" Its biggest trade-off is {disadvantage} ({differences[disadvantage]:.2f} weighted points)."
    # An offer can be worse on a criterion that the traveller gave no weight.
    elif any(top.scores[name] < runner_up.scores[name] for name in CRITERIA):
        text += " It scores lower on a criterion with zero weight."
    else:
        text += " It scores at least as well on the other criteria."
    return text


def rank_offers(
    offers: list[Offer], weights: ScoreWeights = ScoreWeights(), preferred_departure: str = "any"
) -> RankingResult:
    """Rank offers that already passed the hard requirements."""
    if preferred_departure not in DEPARTURE_CHOICES:
        raise ValueError(f"Choose a departure preference from {', '.join(DEPARTURE_CHOICES)}.")
    if not offers:
        return RankingResult(offers=[], notes=[], recommendation=None)

    prices = [offer.price_eur for offer in offers]
    durations = [int((offer.arrives_at - offer.departs_at).total_seconds() // 60) for offer in offers]
    lowest_price, highest_price = min(prices), max(prices)
    shortest, longest = Decimal(min(durations)), Decimal(max(durations))
    percentages = weights.as_dict()
    weight_fractions = {name: Fraction(value) / 100 for name, value in percentages.items()}

    ranked = []
    for offer, duration in zip(offers, durations):
        scores = {
            "price": lower_is_better(offer.price_eur, lowest_price, highest_price),
            "duration": lower_is_better(Decimal(duration), shortest, longest),
            "departure": departure_score(offer.departs_at.time(), preferred_departure),
            "flexibility": Fraction(50 * offer.changeable + 50 * offer.refundable),
        }
        total = sum(scores[name] * weight_fractions[name] for name in CRITERIA)
        # Count tenths and round exact halfway values up, e.g. 9.75 to 9.8.
        tenths = (total * 10 + Fraction(1, 2)) // 1
        shown_total = Decimal(tenths).scaleb(-1)
        shown_scores = {
            name: Decimal(score.numerator) / score.denominator
            for name, score in scores.items()
        }
        ranked.append(RankedOffer(offer, duration, shown_scores, shown_total))

    ranked.sort(key=lambda row: (-row.total, row.offer.price_eur, row.offer.offer_id))
    score_counts = Counter(row.total for row in ranked)
    previous_total = None
    rank = 0
    for position, row in enumerate(ranked, start=1):
        if row.total != previous_total:
            rank = position
        row.rank = rank
        row.tied = score_counts[row.total] > 1
        previous_total = row.total

    notes = []
    if lowest_price == highest_price:
        notes.append("Price gets 50 for every offer because there is no price difference to compare.")
    if shortest == longest:
        notes.append("Duration gets 50 for every offer because there is no duration difference to compare.")
    if preferred_departure == "any":
        notes.append("Any time was selected. Every offer gets 50 for departure, so it does not affect the order.")
    return RankingResult(ranked, notes, _recommendation(ranked, percentages))
