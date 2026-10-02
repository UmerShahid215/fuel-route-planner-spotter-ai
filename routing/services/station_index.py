import threading
from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from .geo import chord_to_miles, miles_to_chord, to_unit_xyz


@dataclass(frozen=True)
class Station:
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    price: float
    lat: float
    lng: float


@dataclass(frozen=True)
class RouteStation:
    station: Station
    mile: float
    off_route_miles: float

    @property
    def price(self):
        return self.station.price


class StationIndex:
    def __init__(self, stations):
        self.stations = list(stations)
        self.lat = np.array([s.lat for s in self.stations], dtype=float)
        self.lng = np.array([s.lng for s in self.stations], dtype=float)
        self.xyz = to_unit_xyz(self.lat, self.lng) if self.stations else np.empty((0, 3))

    @classmethod
    def from_db(cls):
        from routing.models import FuelStation

        rows = FuelStation.objects.values_list(
            "opis_id", "name", "address", "city", "state", "retail_price", "latitude", "longitude"
        )
        return cls(Station(i, n, a, c, s, float(p), la, lo) for i, n, a, c, s, p, la, lo in rows)

    def along_route(self, route_points, route_miles, radius_miles):
        if not self.stations or len(route_points) == 0:
            return []
        pad_lat = radius_miles / 69.0
        pad_lng = radius_miles / (69.0 * max(np.cos(np.radians(np.abs(route_points[:, 0]).max())), 0.1))
        bbox = (
            (self.lat >= route_points[:, 0].min() - pad_lat)
            & (self.lat <= route_points[:, 0].max() + pad_lat)
            & (self.lng >= route_points[:, 1].min() - pad_lng)
            & (self.lng <= route_points[:, 1].max() + pad_lng)
        )
        candidates = np.nonzero(bbox)[0]
        if len(candidates) == 0:
            return []

        tree = cKDTree(to_unit_xyz(route_points[:, 0], route_points[:, 1]))
        dist, nearest = tree.query(self.xyz[candidates], distance_upper_bound=miles_to_chord(radius_miles))
        hits = np.isfinite(dist)
        off_route = chord_to_miles(dist[hits])
        result = [
            RouteStation(self.stations[c], float(route_miles[n]), float(o))
            for c, n, o in zip(candidates[hits], nearest[hits], off_route)
        ]
        return sorted(result, key=lambda rs: (rs.mile, rs.price))


_index = None
_lock = threading.Lock()


def get_station_index():
    global _index
    if _index is None:
        with _lock:
            if _index is None:
                _index = StationIndex.from_db()
    return _index


def reset_station_index():
    global _index
    with _lock:
        _index = None
