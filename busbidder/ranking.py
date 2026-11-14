"""Score eligible offers for the traveller's chosen preferences."""

from decimal import Decimal


def lower_is_better(value: Decimal, minimum: Decimal, maximum: Decimal) -> Decimal:
    """Map a price or duration to the 0–100 scale using the eligible offer range."""
    raise NotImplementedError("Milestone 4: implement and test Min-Max scoring.")
