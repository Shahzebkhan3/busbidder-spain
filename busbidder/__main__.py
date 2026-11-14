"""Run the package with python -m busbidder."""

import argparse
import logging
from pathlib import Path
import sys

from .data_loader import InvalidRecordError, load_offers


def main() -> int:
    """Load and print the offers. Return 0 if successful or 1 if loading fails."""
    # Find the data folder from this file's location, so the path still works
    # when the project is copied to another folder.
    project_dir = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Load and validate BusBidder marketplace data.")
    parser.add_argument("--data-dir", type=Path, default=project_dir / "data")
    args = parser.parse_args()

    try:
        log_dir = project_dir / "logs"
        log_dir.mkdir(exist_ok=True)
        # Set up the log file when the app starts. This lets tests choose
        # where to send log messages when they use the loader directly.
        logging.basicConfig(
            filename=log_dir / "busbidder.log",
            encoding="utf-8",
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )
        offers = load_offers(args.data_dir)
    except (InvalidRecordError, OSError) as error:
        print(f"Unable to load marketplace data: {error}", file=sys.stderr)
        return 1

    print(f"Loaded {len(offers)} valid offers.")
    for offer in offers:
        print(
            f"{offer.offer_id} | {offer.company} | Madrid -> {offer.destination} | "
            f"{offer.departs_at:%Y-%m-%d %H:%M} -> {offer.arrives_at:%Y-%m-%d %H:%M} | "
            f"EUR {offer.price_eur:.2f} | {offer.seats_available} seats"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
