import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import requests
from django.conf import settings

CITY_DATA = Path(__file__).resolve().parent.parent / "data" / "us_city_coords.csv"

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
    "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM",
    "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY",
}
LATLNG_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
CITY_STATE_RE = re.compile(r"^\s*(?P<city>[^,]+?)\s*,\s*(?P<state>[A-Za-z]{2})(?:\s*,?\s*(?:USA?|United States))?\s*$", re.I)
PREFIXES = {"SAINT": "ST", "FORT": "FT", "MOUNT": "MT"}


class GeocodingError(Exception):
    pass


@dataclass(frozen=True)
class Location:
    lat: float
    lng: float
    label: str
    source: str

    def as_dict(self):
        return {"lat": round(self.lat, 6), "lng": round(self.lng, 6), "label": self.label, "source": self.source}


def normalize_city(name):
    words = re.sub(r"[.'\-]", " ", name.upper()).split()
    words = [PREFIXES.get(w, w) for w in words]
    return "".join(words)


@lru_cache(maxsize=1)
def city_table():
    with CITY_DATA.open(newline="") as fh:
        return {
            (normalize_city(row["city"]), row["state"]): (float(row["lat"]), float(row["lng"]))
            for row in csv.DictReader(fh)
        }


def lookup_city(city, state):
    return city_table().get((normalize_city(city), state.strip().upper()))


def in_usa(lat, lng):
    contiguous = 24.0 <= lat <= 49.5 and -125.0 <= lng <= -66.5
    alaska = 51.0 <= lat <= 71.5 and -180.0 <= lng <= -129.0
    hawaii = 18.5 <= lat <= 22.5 and -161.0 <= lng <= -154.5
    return contiguous or alaska or hawaii


def _checked(location):
    if not in_usa(location.lat, location.lng):
        raise GeocodingError(f"'{location.label}' is outside the USA.")
    return location


def geocode(query):
    query = (query or "").strip()
    if not query:
        raise GeocodingError("Location is required.")

    if match := LATLNG_RE.match(query):
        lat, lng = float(match[1]), float(match[2])
        return _checked(Location(lat, lng, query, "coordinates"))

    if (match := CITY_STATE_RE.match(query)) and match["state"].upper() in US_STATES:
        if coords := lookup_city(match["city"], match["state"]):
            return _checked(Location(*coords, f"{match['city'].title()}, {match['state'].upper()}", "local"))

    return _checked(_nominatim(query))


def _nominatim(query):
    cfg = settings.FUEL_ROUTE
    try:
        resp = requests.get(
            f"{cfg['NOMINATIM_URL']}/search",
            params={"q": query, "format": "jsonv2", "countrycodes": "us", "limit": 1},
            headers={"User-Agent": cfg["USER_AGENT"]},
            timeout=cfg["HTTP_TIMEOUT_SECONDS"],
        )
        resp.raise_for_status()
        results = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise GeocodingError(f"Geocoding service failed for '{query}'.") from exc
    if not results:
        raise GeocodingError(f"Could not find a US location matching '{query}'.")
    hit = results[0]
    return Location(float(hit["lat"]), float(hit["lon"]), hit.get("display_name", query), "nominatim")
