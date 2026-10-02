from types import SimpleNamespace

import numpy as np

from routing.models import FuelStation


def cand(mile, price):
    return SimpleNamespace(mile=mile, price=price)


def make_station(opis_id, lat, lng, price, city="Town", state="TX", name=None):
    return FuelStation.objects.create(
        opis_id=opis_id,
        name=name or f"Station {opis_id}",
        address="I-10, EXIT 1",
        city=city,
        state=state,
        rack_id=1,
        retail_price=price,
        latitude=lat,
        longitude=lng,
    )


def osrm_payload(latlon, distance_miles, duration_s=3600.0):
    coords = [[lng, lat] for lat, lng in latlon]
    return {
        "code": "Ok",
        "routes": [{"geometry": {"type": "LineString", "coordinates": coords}, "distance": distance_miles * 1609.344, "duration": duration_s}],
    }


def straight_line(lat, lng_from, lng_to, n=50):
    return np.column_stack((np.full(n, lat), np.linspace(lng_from, lng_to, n)))
