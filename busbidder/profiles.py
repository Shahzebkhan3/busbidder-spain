"""Read named sets of traveller weights from JSON."""

from decimal import Decimal
import json
from pathlib import Path

from .data_loader import InvalidRecordError
from .ranking import CRITERIA, ScoreWeights


CUSTOM_PROFILE = "Custom weights"


def load_profiles(path: Path) -> dict[str, ScoreWeights]:
    """Read the presets and check them with the same rules as manual weights."""
    try:
        with path.open(encoding="utf-8-sig") as source:
            records = json.load(source, parse_float=Decimal)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise InvalidRecordError(f"{path}: invalid JSON: {error}") from error
    if not isinstance(records, dict) or not records:
        raise InvalidRecordError(f"{path}: enter at least one named traveller profile")

    profiles = {}
    for name, weights in records.items():
        if not name.strip() or name == CUSTOM_PROFILE:
            raise InvalidRecordError(f"{path}: invalid profile name {name!r}")
        if not isinstance(weights, dict) or set(weights) != set(CRITERIA):
            raise InvalidRecordError(f"{path}: {name} needs weights for {', '.join(CRITERIA)}")
        if any(type(value) not in (int, Decimal) for value in weights.values()):
            raise InvalidRecordError(f"{path}: {name} weights must be numbers")
        try:
            profiles[name] = ScoreWeights(**{key: Decimal(value) for key, value in weights.items()})
        except ValueError as error:
            raise InvalidRecordError(f"{path}: {name}: {error}") from error
    return profiles
