from dataclasses import dataclass

import numpy as np
import requests
from django.conf import settings

from .geo import METERS_PER_MILE


class RoutingError(Exception):
    pass


@dataclass
class Route:
    latlon: np.ndarray
    distance_miles: float
    duration_seconds: float


def fetch_route(start, finish):
    cfg = settings.FUEL_ROUTE
    coords = f"{start.lng},{start.lat};{finish.lng},{finish.lat}"
    try:
        resp = requests.get(
            f"{cfg['OSRM_BASE_URL']}/route/v1/driving/{coords}",
            params={"overview": "full", "geometries": "geojson", "alternatives": "false", "steps": "false"},
            headers={"User-Agent": cfg["USER_AGENT"]},
            timeout=cfg["HTTP_TIMEOUT_SECONDS"],
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise RoutingError("Routing service is unavailable.") from exc

    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError(data.get("message") or "No drivable route found between these locations.")

    route = data["routes"][0]
    lnglat = np.asarray(route["geometry"]["coordinates"], dtype=float)
    return Route(
        latlon=lnglat[:, ::-1].copy(),
        distance_miles=route["distance"] / METERS_PER_MILE,
        duration_seconds=route["duration"],
    )
