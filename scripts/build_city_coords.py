"""One-off: build routing/data/us_city_coords.csv from the offline `zipcodes` package."""
import csv
from collections import defaultdict
from pathlib import Path

import zipcodes

OUT = Path(__file__).resolve().parent.parent / "routing" / "data" / "us_city_coords.csv"


def main():
    primary, alias = defaultdict(list), defaultdict(list)
    for z in zipcodes.list_all():
        if not z["lat"] or not z["long"]:
            continue
        point = (float(z["lat"]), float(z["long"]))
        primary[(z["city"], z["state"])].append(point)
        for name in z["acceptable_cities"]:
            alias[(name, z["state"])].append(point)
    rows = {}
    for source in (alias, primary):
        for key, pts in source.items():
            rows[key] = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    with OUT.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["city", "state", "lat", "lng"])
        for (city, state), (lat, lng) in sorted(rows.items()):
            w.writerow([city, state, f"{lat:.5f}", f"{lng:.5f}"])
    print(f"wrote {len(rows)} cities to {OUT}")


if __name__ == "__main__":
    main()
