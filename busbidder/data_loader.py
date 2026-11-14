"""Read the CSV files and report which rows contain errors."""

import csv
import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .models import Offer


logger = logging.getLogger(__name__)

OFFER_FIELDS = (
    "offer_id", "company", "destination", "departs_at", "arrives_at",
    "price_eur", "transfers", "changeable", "refundable", "seats_available",
)
OFFER_ID_PATTERN = re.compile(r"O[1-9][0-9]*")


class InvalidRecordError(ValueError):
    """A CSV row has missing or invalid data."""

    pass


def _read_records(
    path: Path, fields: tuple[str, ...], unique_field: str
) -> list[tuple[int, dict[str, str]]]:
    """Check the columns and duplicate IDs, then return rows with line numbers.

    If a quoted value spans several lines, use its last line number.
    The columns can appear in any order.
    """
    records = []
    seen = set()
    line_number = 1
    try:
        # Some UTF-8 files start with a byte-order mark (BOM).
        # utf-8-sig can read files with or without it.
        with path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source, strict=True)
            headers = reader.fieldnames
            # Check the column count too, so repeated column names are caught.
            if headers is None or len(headers) != len(fields) or set(headers) != set(fields):
                raise InvalidRecordError(
                    f"{path}: row 1: expected exactly these columns: {', '.join(fields)}"
                )

            while True:
                line_number = reader.line_num + 1
                row = next(reader, None)
                if row is None:
                    break
                line_number = reader.line_num
                # DictReader uses a None key for extra cells and None values
                # for missing cells. Check these before calling strip().
                if None in row or any(value is None for value in row.values()):
                    raise InvalidRecordError(
                        f"{path}: row {line_number}: wrong number of fields"
                    )
                row = {name: value.strip() for name, value in row.items()}
                empty = [name for name, value in row.items() if not value]
                if empty:
                    raise InvalidRecordError(
                        f"{path}: row {line_number}: missing value for {', '.join(empty)}"
                    )
                identifier = row[unique_field]
                if identifier in seen:
                    raise InvalidRecordError(
                        f"{path}: row {line_number}: duplicate {unique_field} '{identifier}'"
                    )
                seen.add(identifier)
                records.append((line_number, row))
    except (csv.Error, UnicodeError) as error:
        raise InvalidRecordError(
            f"{path}: near row {line_number}: invalid UTF-8 CSV: {error}"
        ) from error
    return records


def _parse_datetime(value: str, field: str) -> datetime:
    """Read a date and time in YYYY-MM-DDTHH:MM format, using local mainland time."""
    try:
        result = datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError as error:
        raise ValueError(f"{field} must be a valid date/time in YYYY-MM-DDTHH:MM format") from error
    # strptime can accept 7 for July. This check requires 07 as documented.
    if result.isoformat(timespec="minutes") != value:
        raise ValueError(f"{field} must use YYYY-MM-DDTHH:MM format")
    return result


def _parse_price(value: str) -> Decimal:
    """Read a price of zero or more with up to two decimal places."""
    try:
        # Read the price straight from text to avoid float rounding errors.
        price = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("price_eur must be a number") from error
    # Decimal accepts NaN and Infinity, but neither is a valid price.
    if not price.is_finite() or price < 0:
        raise ValueError("price_eur must be finite and non-negative")
    # Report extra decimal places so the price can be corrected in the CSV.
    if price.as_tuple().exponent < -2:
        raise ValueError("price_eur must have at most two decimal places")
    return price


def _parse_count(value: str, field: str) -> int:
    """Read a whole number of zero or more. A sold-out bus has zero seats."""
    if not value.isascii() or not value.isdecimal():
        raise ValueError(f"{field} must be a non-negative integer")
    return int(value)


def _parse_bool(value: str, field: str) -> bool:
    """Read true or false, allowing upper- or lowercase letters."""
    # bool("false") gives True because the string has text in it.
    # Compare the words directly to get the right value.
    if value.lower() not in ("true", "false"):
        raise ValueError(f"{field} must be true or false")
    return value.lower() == "true"


def _parse_offer(
    row: dict[str, str], companies: dict[str, str], destinations: set[str]
) -> Offer:
    """Check an offer's fields, company and destination, then create an Offer."""
    if OFFER_ID_PATTERN.fullmatch(row["offer_id"]) is None:
        raise ValueError("offer_id must be O followed by a positive integer, such as O1")
    if row["company"] not in companies:
        raise ValueError(f"unknown company '{row['company']}'")
    if row["destination"] not in destinations:
        raise ValueError(f"unknown destination '{row['destination']}'")

    departure = _parse_datetime(row["departs_at"], "departs_at")
    arrival = _parse_datetime(row["arrives_at"], "arrives_at")
    # An overnight arrival needs the next day's date in the CSV.
    # Compare the dates as well as the times to check this correctly.
    if arrival <= departure:
        raise ValueError("arrives_at must be after departs_at; include the next date for overnight travel")

    return Offer(
        offer_id=row["offer_id"],
        company=row["company"],
        destination=row["destination"],
        departs_at=departure,
        arrives_at=arrival,
        price_eur=_parse_price(row["price_eur"]),
        transfers=_parse_count(row["transfers"], "transfers"),
        changeable=_parse_bool(row["changeable"], "changeable"),
        refundable=_parse_bool(row["refundable"], "refundable"),
        seats_available=_parse_count(row["seats_available"], "seats_available"),
    )


def load_offers(data_dir: Path) -> list[Offer]:
    """Load all offers. Stop and report an error if any record is invalid.

    Bad records raise InvalidRecordError with the file and row number.
    File problems raise standard Python errors, such as FileNotFoundError.
    main() sets up the log file when the application starts.

    A file with just the correct offer headers returns an empty list.
    Offers with zero seats are loaded here and will be excluded during filtering.
    """
    data_dir = Path(data_dir)
    logger.info("Loading marketplace data from %s", data_dir)
    try:
        company_path = data_dir / "companies.csv"
        companies = {
            row["name"]: row["profile"]
            for _, row in _read_records(company_path, ("name", "profile"), "name")
        }
        if not companies:
            raise InvalidRecordError(f"{company_path}: no companies found")

        destination_path = data_dir / "destinations.csv"
        destinations = {
            row["name"]
            for _, row in _read_records(destination_path, ("name",), "name")
        }
        if not destinations:
            raise InvalidRecordError(f"{destination_path}: no destinations found")

        offer_path = data_dir / "offers.csv"
        # Return the list only after all rows pass, so a bad row cannot leave
        # the application comparing an incomplete set of offers.
        offers = []
        for line_number, row in _read_records(offer_path, OFFER_FIELDS, "offer_id"):
            try:
                offers.append(_parse_offer(row, companies, destinations))
            except ValueError as error:
                raise InvalidRecordError(f"{offer_path}: row {line_number}: {error}") from error
    except (InvalidRecordError, OSError) as error:
        logger.error("Marketplace load failed: %s", error)
        raise

    logger.info(
        "Loaded %d companies, %d destinations and %d offers",
        len(companies), len(destinations), len(offers),
    )
    return offers
