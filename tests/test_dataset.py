"""Check full route coverage and that the offer data can be rebuilt."""

import csv
from pathlib import Path
import subprocess
import sys

from busbidder.data_loader import load_destinations, load_offers


PROJECT = Path(__file__).resolve().parents[1]
DATA = PROJECT / "data"


def test_full_marketplace_covers_every_company_destination_pair(sample_data):
    with (DATA / "companies.csv").open(encoding="utf-8", newline="") as source:
        companies = {row["name"] for row in csv.DictReader(source)}
    destinations = load_destinations(DATA)
    offers = load_offers(DATA)
    assert len(companies) == 5
    assert len(destinations) == 15
    assert len(offers) == 76
    assert {(offer.company, offer.destination) for offer in offers} == {
        (company, destination) for company in companies for destination in destinations
    }
    assert [offer for offer in offers if offer.destination == "Malaga"] == load_offers(sample_data)


def test_generation_matches_the_committed_offers():
    result = subprocess.run(
        [sys.executable, "-B", str(PROJECT / "scripts" / "generate_offers.py"), "--check"],
        cwd=PROJECT, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
