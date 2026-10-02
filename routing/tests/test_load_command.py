import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import CommandError, call_command
from django.test import TestCase

from routing.models import FuelStation

CSV = """OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price
7,WOODSHED OF BIG CABIN,"I-44, EXIT 283",Big Cabin,OK,307,3.00733333
20,PILOT #1243,"I-8, EXIT 119",Gila Bend,AZ,930,3.899
20,PILOT TRAVEL CENTER #1243,"I-8, EXIT 119",Gila Bend,AZ,930,3.799
20,PILOT DUP,"I-8, EXIT 119",Gila Bend,AZ,930,3.999
30,FLYING J,"HWY 2",Calgary,AB,1,1.5
40,NOWHERE STOP,"HWY 9",Atlantisville,TX,,3.1
50,BAD ROW,"HWY 9",Austin,TX,,n/a
"""


class LoadFuelStationsTests(TestCase):
    def run_command(self, content=CSV):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
            fh.write(content)
        out = StringIO()
        call_command("load_fuel_stations", csv=fh.name, stdout=out)
        Path(fh.name).unlink()
        return out.getvalue()

    def test_loads_dedupes_and_skips(self):
        out = self.run_command()
        self.assertIn("Loaded 2 US stations", out)
        self.assertIn("Skipped 1 non-US rows; 1 unmatched", out)
        self.assertIn("Atlantisville, TX", out)
        pilot = FuelStation.objects.get(opis_id=20)
        self.assertEqual(str(pilot.retail_price), "3.7990")
        self.assertEqual(pilot.name, "PILOT TRAVEL CENTER #1243")
        self.assertIn("Gila Bend", str(pilot))

    def test_reload_replaces_existing(self):
        self.run_command()
        self.run_command()
        self.assertEqual(FuelStation.objects.count(), 2)

    def test_missing_file(self):
        with self.assertRaises(CommandError):
            call_command("load_fuel_stations", csv="/does/not/exist.csv")

    def test_bundled_dataset(self):
        out = StringIO()
        call_command("load_fuel_stations", stdout=out)
        self.assertGreater(FuelStation.objects.count(), 6000)
