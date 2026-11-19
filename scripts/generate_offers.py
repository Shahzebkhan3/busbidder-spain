"""Rebuild the fictional marketplace from the sample and route baselines."""

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import io
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@dataclass(frozen=True)
class Service:
    company: str
    departure: datetime
    price_factor: str
    extra_minutes: int
    changeable: bool
    refundable: bool
    seats: int


SERVICES = (
    Service("SolRuta", datetime(2027, 7, 12, 8, 30), "0.85", 20, False, False, 20),
    Service("Camino Express", datetime(2027, 7, 13, 9), "1.18", -35, True, True, 12),
    Service("CostaLink", datetime(2027, 7, 12, 11, 15), "1.00", 25, True, False, 12),
    Service("VerdeBus", datetime(2027, 7, 14, 7, 45), "1.03", 10, True, False, 9),
    Service("NocheVia", datetime(2027, 7, 13, 23, 30), "0.73", 45, True, False, 15),
)


def build_csv(data_dir: Path = DATA_DIR) -> str:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    with (data_dir / "malaga_sample.csv").open(encoding="utf-8", newline="") as source:
        sample = list(csv.reader(source))
    writer.writerows(sample)
    offer_number = int(sample[-1][0][1:]) + 1
    with (data_dir / "route_baselines.csv").open(encoding="utf-8", newline="") as source:
        for route in csv.DictReader(source):
            base_duration = int(route["duration_minutes"])
            base_price = Decimal(route["price_eur"])
            for service in SERVICES:
                duration = base_duration + service.extra_minutes
                price_factor = Decimal(service.price_factor)
                transfers = int(service.company == "SolRuta" and base_duration >= 300)
                if service.company == "CostaLink" and route["coastal"] == "true":
                    duration = base_duration - 15
                    price_factor = Decimal("0.95")
                arrival = service.departure + timedelta(minutes=duration)
                price = (base_price * price_factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                writer.writerow((
                    f"O{offer_number}", service.company, route["destination"],
                    service.departure.isoformat(timespec="minutes"), arrival.isoformat(timespec="minutes"),
                    price, transfers, str(service.changeable).lower(), str(service.refundable).lower(),
                    service.seats,
                ))
                offer_number += 1
    return output.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DATA_DIR / "offers.csv")
    parser.add_argument("--check", action="store_true", help="compare without writing a file")
    args = parser.parse_args()
    generated = build_csv()
    if args.check:
        if args.output.read_text(encoding="utf-8") != generated:
            print("The offer file differs from the generated dataset.")
            return 1
        print("The offer file matches the generated dataset.")
    else:
        args.output.write_text(generated, encoding="utf-8", newline="\n")
        print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
