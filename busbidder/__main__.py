"""Run the package with python -m busbidder."""

import argparse
from datetime import date
from decimal import Decimal, InvalidOperation
import logging
from pathlib import Path
import sys

from .data_loader import InvalidRecordError, load_offers
from .filtering import filter_offers
from .models import InvalidRequestError, Offer, TravelRequest


def _request_from_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> TravelRequest | None:
    """Build a search request, or return None when only loading data."""
    search_values = (args.destination, args.from_date, args.to_date, args.max_price, args.max_transfers)
    if all(value is None for value in search_values) and not args.require_changeable:
        return None
    if args.destination is None or args.from_date is None or args.to_date is None:
        parser.error("A search needs --destination, --from-date and --to-date.")

    try:
        budget = Decimal(args.max_price) if args.max_price is not None else None
    except InvalidOperation:
        parser.error("--max-price must be a number, such as 50.00.")
    try:
        return TravelRequest(
            destination=args.destination,
            first_departure_date=args.from_date,
            last_departure_date=args.to_date,
            max_price_eur=budget,
            max_transfers=args.max_transfers,
            require_changeable=args.require_changeable,
        )
    except InvalidRequestError as error:
        parser.error(str(error))


def _show_offers(offers: list[Offer]) -> None:
    """Print the same offer details for loading and search results."""
    for offer in offers:
        print(
            f"{offer.offer_id} | {offer.company} | Madrid -> {offer.destination} | "
            f"{offer.departs_at:%Y-%m-%d %H:%M} -> {offer.arrives_at:%Y-%m-%d %H:%M} | "
            f"EUR {offer.price_eur:.2f} | {offer.seats_available} seats"
        )


def main() -> int:
    """Load offers and optionally search them. Invalid command arguments exit with 2."""
    # Find the data folder from this file's location, so the path still works
    # when the project is copied to another folder.
    project_dir = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Load bus offers and search by journey requirements.")
    parser.add_argument("--data-dir", type=Path, default=project_dir / "data")
    parser.add_argument("--destination", help="destination name, such as Malaga")
    parser.add_argument("--from-date", type=date.fromisoformat, help="first departure date (YYYY-MM-DD)")
    parser.add_argument("--to-date", type=date.fromisoformat, help="last departure date (YYYY-MM-DD)")
    parser.add_argument("--max-price", help="maximum ticket price in EUR")
    parser.add_argument("--max-transfers", type=int, help="maximum number of transfers")
    parser.add_argument("--require-changeable", action="store_true", help="only allow changeable tickets")
    args = parser.parse_args()
    request = _request_from_args(parser, args)

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
    if request is None:
        _show_offers(offers)
        return 0

    result = filter_offers(offers, request)
    print(f"{len(result.accepted)} offers match your requirements.")
    if not result.accepted:
        print("No offers matched. Review your requirements and any rejection reasons below.")
    _show_offers(result.accepted)
    if result.rejected:
        print("Rejected offers:")
        for offer_id, reasons in result.rejected.items():
            print(f"{offer_id} | " + " ".join(reasons))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
