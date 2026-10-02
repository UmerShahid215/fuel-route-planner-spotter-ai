import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from routing.models import FuelStation
from routing.services.geocoding import US_STATES, lookup_city
from routing.services.station_index import reset_station_index

DEFAULT_CSV = Path(__file__).resolve().parents[2] / "data" / "fuel_prices.csv"


class Command(BaseCommand):
    help = "Load fuel stations from the OPIS CSV and geocode them offline by city/state."

    def add_arguments(self, parser):
        parser.add_argument("--csv", default=str(DEFAULT_CSV), help="Path to the fuel prices CSV.")

    def handle(self, *args, **options):
        path = Path(options["csv"])
        if not path.exists():
            raise CommandError(f"CSV not found: {path}")

        stations, skipped_state, unmatched = {}, 0, set()
        with path.open(newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                state, city = row["State"].strip().upper(), row["City"].strip()
                if state not in US_STATES:
                    skipped_state += 1
                    continue
                try:
                    opis_id, price = int(row["OPIS Truckstop ID"]), Decimal(row["Retail Price"])
                except (ValueError, InvalidOperation):
                    continue
                if opis_id in stations and stations[opis_id].retail_price <= price:
                    continue
                coords = lookup_city(city, state)
                if coords is None:
                    unmatched.add(f"{city}, {state}")
                    continue
                stations[opis_id] = FuelStation(
                    opis_id=opis_id,
                    name=row["Truckstop Name"].strip(),
                    address=row["Address"].strip(),
                    city=city,
                    state=state,
                    rack_id=int(row["Rack ID"]) if row.get("Rack ID", "").strip().isdigit() else None,
                    retail_price=price.quantize(Decimal("0.0001")),
                    latitude=coords[0],
                    longitude=coords[1],
                )

        with transaction.atomic():
            FuelStation.objects.all().delete()
            FuelStation.objects.bulk_create(stations.values(), batch_size=1000)
        reset_station_index()

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(stations)} US stations."))
        self.stdout.write(f"Skipped {skipped_state} non-US rows; {len(unmatched)} unmatched cities.")
        if unmatched:
            self.stdout.write("Unmatched: " + "; ".join(sorted(unmatched)[:20]))
