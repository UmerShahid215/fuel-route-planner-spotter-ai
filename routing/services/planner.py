import hashlib
import json
import time

from django.conf import settings
from django.core.cache import cache

from .geo import densify
from .geocoding import geocode
from .optimizer import plan_fuel_stops
from .routing_client import fetch_route
from .station_index import get_station_index


def _cache_key(prefix, *parts):
    raw = json.dumps(parts, sort_keys=True, default=str).lower()
    return f"{prefix}:{hashlib.sha1(raw.encode()).hexdigest()}"


def _cached_geocode(query, calls):
    key = _cache_key("geo", query.strip())
    if (loc := cache.get(key)) is None:
        loc = geocode(query)
        if loc.source == "nominatim":
            calls["geocoding"] += 1
        cache.set(key, loc, settings.FUEL_ROUTE["CACHE_SECONDS"])
    return loc


def _cached_route(start, finish, calls):
    key = _cache_key("route", round(start.lat, 5), round(start.lng, 5), round(finish.lat, 5), round(finish.lng, 5))
    if (route := cache.get(key)) is None:
        route = fetch_route(start, finish)
        calls["routing"] += 1
        cache.set(key, route, settings.FUEL_ROUTE["CACHE_SECONDS"])
    return route


def plan_trip(start_query, finish_query, start_fuel_gallons=None):
    t0 = time.perf_counter()
    cfg = settings.FUEL_ROUTE
    range_miles, mpg = cfg["VEHICLE_RANGE_MILES"], cfg["MILES_PER_GALLON"]
    tank_gallons = range_miles / mpg
    start_fuel_gallons = tank_gallons if start_fuel_gallons is None else min(start_fuel_gallons, tank_gallons)
    calls = {"routing": 0, "geocoding": 0}

    start = _cached_geocode(start_query, calls)
    finish = _cached_geocode(finish_query, calls)
    route = _cached_route(start, finish, calls)

    points, miles = densify(route.latlon, step_miles=1.0)
    if miles[-1] > 0:
        miles = miles * (route.distance_miles / miles[-1])

    radius = cfg["STATION_SEARCH_RADIUS_MILES"]
    candidates = get_station_index().along_route(points, miles, radius)
    plan = plan_fuel_stops(
        candidates,
        total_miles=route.distance_miles,
        range_miles=range_miles,
        mpg=mpg,
        start_fuel_miles=start_fuel_gallons * mpg,
        start_grace_miles=radius,
        stop_penalty=cfg["STOP_PENALTY_USD"],
    )

    stops = [
        {
            "stop": n,
            "opis_id": s.candidate.station.opis_id,
            "name": s.candidate.station.name,
            "address": s.candidate.station.address,
            "city": s.candidate.station.city,
            "state": s.candidate.station.state,
            "lat": round(s.candidate.station.lat, 6),
            "lng": round(s.candidate.station.lng, 6),
            "price_per_gallon": round(s.candidate.price, 3),
            "mile_marker": round(s.candidate.mile, 1),
            "off_route_miles": round(s.candidate.off_route_miles, 1),
            "fuel_on_arrival_gallons": round(s.fuel_on_arrival_gallons, 2),
            "gallons": round(s.gallons, 2),
            "cost": round(s.cost, 2),
        }
        for n, s in enumerate(plan.stops, start=1)
    ]

    return {
        "start": start.as_dict(),
        "finish": finish.as_dict(),
        "route": {
            "distance_miles": round(float(route.distance_miles), 1),
            "duration_hours": round(float(route.duration_seconds) / 3600, 2),
            "geometry": {"type": "LineString", "coordinates": route.latlon[:, ::-1].round(5).tolist()},
        },
        "fuel_stops": stops,
        "summary": {
            "total_fuel_cost": round(float(plan.total_cost), 2),
            "total_gallons_purchased": round(float(plan.total_gallons), 2),
            "total_gallons_used": round(float(route.distance_miles) / mpg, 2),
            "number_of_stops": len(stops),
            "start_fuel_gallons": round(start_fuel_gallons, 2),
            "vehicle_range_miles": range_miles,
            "miles_per_gallon": mpg,
            "stations_considered": len(candidates),
        },
        "external_api_calls": calls,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
