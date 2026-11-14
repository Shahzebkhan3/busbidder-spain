"""Read and validate the marketplace data."""

from pathlib import Path

from .models import Offer


class InvalidRecordError(ValueError):
    """A source record is invalid, such as a fare with a negative price."""

    pass


def load_offers(data_dir: Path) -> list[Offer]:
    """Read offers and check company and destination references in the data directory."""
    raise NotImplementedError("Milestone 2: load and validate the sample data.")
