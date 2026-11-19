"""Run the package with python -m busbidder."""

import argparse
from datetime import date
from decimal import Decimal, InvalidOperation
import logging
from pathlib import Path
import sys

from .booking import BOOKINGS_FILENAME, BookingError, BookingStore
from .data_loader import InvalidRecordError, load_destinations, load_offers
from .experiments import write_comparisons
from .filtering import filter_offers
from .models import InvalidRequestError, Offer, TravelRequest
from .profiles import load_profiles
from .ranking import DEPARTURE_CHOICES, RankingResult, ScoreWeights, rank_offers


def _request_from_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> TravelRequest | None:
    """Build a search request, or return None when only loading data."""
    search_values = (
        args.destination, args.from_date, args.to_date, args.max_price,
        args.max_transfers, args.departure, args.weights, args.book,
    )
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


def _offer_details(offer: Offer) -> str:
    return (
        f"{offer.offer_id} | {offer.company} | Madrid -> {offer.destination} | "
        f"{offer.departs_at:%Y-%m-%d %H:%M} -> {offer.arrives_at:%Y-%m-%d %H:%M} | "
        f"EUR {offer.price_eur:.2f} | {offer.seats_available} seats"
    )


def _show_ranking(result: RankingResult, weights: ScoreWeights, preferred_departure: str) -> None:
    print("Weights: " + ", ".join(f"{name} {value}%" for name, value in weights.as_dict().items()))
    print(f"Preferred departure: {'any time' if preferred_departure == 'any' else preferred_departure}")
    for row in result.offers:
        rank = f"={row.rank}" if row.tied else str(row.rank)
        print(f"{rank}. {_offer_details(row.offer)}")
        change = "yes" if row.offer.changeable else "no"
        refund = "yes" if row.offer.refundable else "no"
        print(f"   {row.duration_minutes} min | transfers {row.offer.transfers} | changeable {change} | refundable {refund}")
        components = " | ".join(f"{name} {score:.1f}" for name, score in row.scores.items())
        print(f"   Total {row.total:.1f}/100 | {components}")
    for note in result.notes:
        print(note)
    if result.recommendation:
        print(result.recommendation)


def main() -> int:
    """Load offers, search them, and optionally book a matching offer."""
    # Find the data folder from this file's location, so the path still works
    # when the project is copied to another folder.
    project_dir = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Open BusBidder Spain or search from the command line.")
    parser.add_argument("--data-dir", type=Path, default=project_dir / "data")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true", help="list offers in the terminal without ranking them")
    mode.add_argument("--compare", action="store_true", help="reproduce the Malaga comparison tables")
    parser.add_argument("--results-dir", type=Path, help="output folder for --compare")
    parser.add_argument("--destination", help="destination name, such as Malaga")
    parser.add_argument("--from-date", type=date.fromisoformat, help="first departure date (YYYY-MM-DD)")
    parser.add_argument("--to-date", type=date.fromisoformat, help="last departure date (YYYY-MM-DD)")
    parser.add_argument("--max-price", help="maximum ticket price in EUR")
    parser.add_argument("--max-transfers", type=int, help="maximum number of transfers")
    parser.add_argument("--require-changeable", action="store_true", help="only allow changeable tickets")
    parser.add_argument("--departure", choices=DEPARTURE_CHOICES, help="preferred departure period (default: any)")
    parser.add_argument(
        "--weights", nargs=4, metavar=("PRICE", "DURATION", "DEPARTURE", "FLEXIBILITY"),
        help="four percentages adding up to 100 (default: 40 25 15 20)",
    )
    parser.add_argument("--book", metavar="OFFER_ID", help="book one seat on a matching offer")
    parser.add_argument("--bookings-file", type=Path, help="use a separate file for saved bookings")
    args = parser.parse_args()
    request = _request_from_args(parser, args)
    if args.list and request is not None:
        parser.error("Use --list by itself or supply search arguments.")
    if args.compare and (request is not None or args.bookings_file is not None):
        parser.error("--compare uses the fixed Malaga request and the original CSV capacity.")
    if args.results_dir is not None and not args.compare:
        parser.error("--results-dir requires --compare.")
    show_window = request is None and not (args.list or args.compare)
    weights = ScoreWeights()
    if args.weights is not None:
        try:
            weights = ScoreWeights(*(Decimal(value) for value in args.weights))
        except InvalidOperation:
            parser.error("--weights must contain four numbers.")
        except ValueError as error:
            parser.error(str(error))

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
        if show_window:
            destinations = load_destinations(args.data_dir)
        if show_window or args.compare:
            profiles = load_profiles(project_dir / "data" / "profiles.json")
    except (InvalidRecordError, OSError) as error:
        print(f"Unable to load marketplace data: {error}", file=sys.stderr)
        return 1

    if args.compare:
        try:
            results_dir = args.results_dir or project_dir / "results"
            paths = write_comparisons(offers, profiles, results_dir)
        except (ValueError, OSError) as error:
            print(f"Unable to write the comparison: {error}", file=sys.stderr)
            return 1
        for path in paths:
            print(f"Wrote {path}")
        return 0

    try:
        booking_path = args.bookings_file or args.data_dir / BOOKINGS_FILENAME
        booking_store = BookingStore(booking_path, offers)
        available = booking_store.available_offers()
    except (BookingError, OSError) as error:
        print(f"Unable to check seat availability: {error}", file=sys.stderr)
        return 1

    if show_window:
        try:
            from .gui import launch
        except ImportError:
            print("Tkinter is unavailable. Install Python with Tcl/Tk support or use --list.", file=sys.stderr)
            return 1
        return launch(booking_store, sorted(destinations), offers, profiles)

    print(f"Loaded {len(available)} valid offers.")
    if request is None:
        for offer in available:
            print(_offer_details(offer))
        return 0

    result = filter_offers(available, request)
    print(f"{len(result.accepted)} offers match your requirements.")
    if not result.accepted:
        print("No offers matched. Review your requirements and any rejection reasons below.")
    else:
        preferred_departure = args.departure or "any"
        ranking = rank_offers(result.accepted, weights, preferred_departure)
        _show_ranking(ranking, weights, preferred_departure)
    if result.rejected:
        print("Rejected offers:")
        for offer_id, reasons in result.rejected.items():
            print(f"{offer_id} | " + " ".join(reasons))

    if args.book is not None:
        if args.book in result.rejected:
            print(f"Cannot book {args.book}. " + " ".join(result.rejected[args.book]), file=sys.stderr)
            return 1
        try:
            booking = booking_store.confirm_booking(args.book)
        except BookingError as error:
            print(f"Unable to book: {error}", file=sys.stderr)
            return 1
        print(f"Booking confirmed: {booking.reference}")
        print(f"One seat on {booking.offer_id} with {booking.company} | EUR {booking.price_eur:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
