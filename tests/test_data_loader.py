"""Exercise the public loader using independent copies of the sample CSV files."""

import csv
import logging
import shutil
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from busbidder.data_loader import InvalidRecordError, load_offers


PROJECT_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def data_dir(tmp_path):
    return Path(shutil.copytree(PROJECT_DIR / "data", tmp_path / "data"))


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        return reader.fieldnames, list(reader)


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def change_first_offer(data_dir, field, value):
    path = data_dir / "offers.csv"
    fields, rows = read_csv(path)
    rows[0][field] = value
    write_csv(path, fields, rows)


def test_sample_loads_with_correct_types_and_values(data_dir, caplog):
    with caplog.at_level(logging.INFO, logger="busbidder.data_loader"):
        offers = load_offers(data_dir)

    assert [offer.offer_id for offer in offers] == ["O1", "O2", "O3", "O4", "O5", "O6"]
    first = offers[0]
    assert first.company == "SolRuta"
    assert first.destination == "Malaga"
    assert first.departs_at == datetime(2027, 7, 12, 8, 30)
    assert first.price_eur == Decimal("29.00")
    assert isinstance(first.price_eur, Decimal)
    assert first.transfers == 1
    assert first.changeable is False
    assert offers[1].refundable is True
    assert first.seats_available == 20
    assert "Loaded 5 companies, 15 destinations and 6 offers" in caplog.text


def test_overnight_arrival_uses_next_date(data_dir):
    overnight = next(offer for offer in load_offers(data_dir) if offer.offer_id == "O5")
    assert overnight.arrives_at == datetime(2027, 7, 14, 7, 30)
    assert overnight.arrives_at - overnight.departs_at == timedelta(hours=8)


@pytest.mark.parametrize("filename", ["companies.csv", "destinations.csv", "offers.csv"])
def test_missing_file_reports_path_and_logs_error(data_dir, filename, caplog):
    missing = data_dir / filename
    missing.unlink()
    with pytest.raises(FileNotFoundError) as caught:
        load_offers(data_dir)
    assert Path(caught.value.filename) == missing
    assert "Marketplace load failed" in caplog.text
    assert filename in caplog.text


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("offer_id", "bad-id", "offer_id"),
        ("offer_id", "O0", "offer_id"),
        ("offer_id", "O1extra", "offer_id"),
        ("company", "Unknown Bus", "unknown company"),
        ("destination", "Paris", "unknown destination"),
        ("price_eur", "-0.01", "price_eur"),
        ("price_eur", "NaN", "price_eur"),
        ("price_eur", "Infinity", "price_eur"),
        ("price_eur", "abc", "price_eur"),
        ("price_eur", "29.001", "price_eur"),
        ("price_eur", "", "missing value for price_eur"),
        ("departs_at", "2027-02-30T08:30", "departs_at"),
        ("departs_at", "2027-07-12T25:30", "departs_at"),
        ("departs_at", "2027-7-12T08:30", "departs_at"),
        ("arrives_at", "2027-07-12T08:29", "arrives_at must be after"),
        ("arrives_at", "2027-07-12T08:30", "arrives_at must be after"),
        ("transfers", "-1", "transfers"),
        ("transfers", "1.5", "transfers"),
        ("seats_available", "-1", "seats_available"),
        ("seats_available", "2.5", "seats_available"),
        ("changeable", "yes", "changeable"),
        ("refundable", "0", "refundable"),
    ],
)
def test_invalid_offer_reports_field_file_and_row(data_dir, field, value, reason):
    change_first_offer(data_dir, field, value)
    with pytest.raises(InvalidRecordError) as caught:
        load_offers(data_dir)
    message = str(caught.value)
    assert "offers.csv: row 2:" in message
    assert reason in message


def test_zero_price_transfers_and_seats_are_valid_data(data_dir):
    for field in ("price_eur", "transfers", "seats_available"):
        change_first_offer(data_dir, field, "0")
    offer = load_offers(data_dir)[0]
    assert offer.price_eur == Decimal("0")
    assert offer.transfers == 0
    assert offer.seats_available == 0


def test_whitespace_and_boolean_case_are_normalised(data_dir):
    change_first_offer(data_dir, "company", " SolRuta ")
    change_first_offer(data_dir, "changeable", " TRUE ")
    offer = load_offers(data_dir)[0]
    assert offer.company == "SolRuta"
    assert offer.changeable is True


@pytest.mark.parametrize("filename", ["companies.csv", "destinations.csv", "offers.csv"])
def test_duplicate_identifiers_are_rejected(data_dir, filename):
    path = data_dir / filename
    fields, rows = read_csv(path)
    rows.append(rows[0])
    write_csv(path, fields, rows)
    with pytest.raises(InvalidRecordError, match="duplicate"):
        load_offers(data_dir)


@pytest.mark.parametrize("filename", ["companies.csv", "destinations.csv", "offers.csv"])
def test_empty_file_is_rejected(data_dir, filename):
    (data_dir / filename).write_text("", encoding="utf-8")
    with pytest.raises(InvalidRecordError, match="row 1: expected"):
        load_offers(data_dir)


@pytest.mark.parametrize("filename", ["companies.csv", "destinations.csv"])
def test_catalogue_with_only_header_is_rejected(data_dir, filename):
    path = data_dir / filename
    fields, _ = read_csv(path)
    write_csv(path, fields, [])
    with pytest.raises(InvalidRecordError, match="no .* found"):
        load_offers(data_dir)


def test_offers_header_without_rows_is_an_empty_marketplace(data_dir):
    path = data_dir / "offers.csv"
    fields, _ = read_csv(path)
    write_csv(path, fields, [])
    assert load_offers(data_dir) == []


@pytest.mark.parametrize("problem", ["missing_column", "duplicate_column", "extra_cell", "missing_cell", "bad_quote"])
def test_malformed_csv_is_rejected(data_dir, problem):
    path = data_dir / "offers.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    if problem == "missing_column":
        lines[0] = lines[0].replace("price_eur,", "")
    elif problem == "duplicate_column":
        lines[0] = lines[0].replace("price_eur", "transfers")
    elif problem == "extra_cell":
        lines[1] += ",unexpected"
    elif problem == "missing_cell":
        lines[1] = lines[1].rsplit(",", 1)[0]
    else:
        lines[1] = '"unterminated'
    path.write_text("\n".join(lines), encoding="utf-8")
    with pytest.raises(InvalidRecordError):
        load_offers(data_dir)


def test_invalid_encoding_is_reported_as_invalid_record(data_dir):
    (data_dir / "offers.csv").write_bytes(b"\xff\xfe\xff")
    with pytest.raises(InvalidRecordError, match="invalid UTF-8 CSV"):
        load_offers(data_dir)


def test_utf8_bom_is_accepted(data_dir):
    path = data_dir / "offers.csv"
    original = path.read_text(encoding="utf-8")
    path.write_text(original, encoding="utf-8-sig")
    assert len(load_offers(data_dir)) == 6


def test_late_invalid_record_fails_whole_load_without_changing_files(data_dir, caplog):
    path = data_dir / "offers.csv"
    fields, rows = read_csv(path)
    rows[-1]["price_eur"] = "-1"
    write_csv(path, fields, rows)
    before = {file.name: file.read_bytes() for file in data_dir.iterdir()}
    with caplog.at_level(logging.INFO, logger="busbidder.data_loader"):
        with pytest.raises(InvalidRecordError, match="row 7"):
            load_offers(data_dir)
    assert "Marketplace load failed" in caplog.text
    assert "Loaded 5 companies" not in caplog.text
    assert before == {file.name: file.read_bytes() for file in data_dir.iterdir()}
