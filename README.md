# Fuel Route Planner API

A Django + DRF API that takes a start and finish location in the USA and returns:

- the driving route (GeoJSON) and a link to an interactive map,
- the most cost-effective fuel stops along the route, given a **500-mile range** and **10 MPG**,
- the total fuel cost.

It calls the external routing API **once** per new route, and **zero** times for a repeat request.

## Stack

- Django 6.1, Django REST Framework 3.18
- [OSRM](https://project-osrm.org/) public server for routing (free, no API key)
- NumPy + SciPy (`cKDTree`) to match stations to the route
- Leaflet + OpenStreetMap tiles for the map page
- Nominatim as an optional geocoding fallback, used only for free-text addresses

## Quick start

Requires Python 3.12+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py load_fuel_stations      # loads + geocodes the 8k-row CSV in ~2s
python manage.py runserver
```

## API

### `GET /api/route/` or `POST /api/route/`

| Param                | Required | Description                                                                 |
|----------------------|----------|-----------------------------------------------------------------------------|
| `start`, `finish`    | yes      | `"City, ST"` (resolved offline), `"lat,lng"`, or a free-text US address      |
| `start_fuel_gallons` | no       | Fuel in the tank at departure, from 0 to 50. Defaults to a full tank (50 gal)        |
| `include_geometry`   | no       | Set to `false` to leave the route polyline out of the response                     |

```bash
curl "http://127.0.0.1:8000/api/route/?start=New%20York,%20NY&finish=Los%20Angeles,%20CA"
```

Example response (shortened, values illustrative):

```json
{
  "start":  {"lat": 40.71, "lng": -73.99, "label": "New York, NY", "source": "local"},
  "finish": {"lat": 34.05, "lng": -118.26, "label": "Los Angeles, CA", "source": "local"},
  "route":  {"distance_miles": 2790.4, "duration_hours": 41.2, "geometry": {"type": "LineString", "coordinates": [[-73.99, 40.71], "..."]}},
  "fuel_stops": [
    {"stop": 1, "name": "PILOT #...", "city": "...", "state": "OH", "price_per_gallon": 2.999,
     "mile_marker": 580.9, "off_route_miles": 2.1, "fuel_on_arrival_gallons": 0.0, "gallons": 44.13, "cost": 132.34}
  ],
  "summary": {
    "total_fuel_cost": 727.14,
    "total_gallons_purchased": 236.52,
    "total_gallons_used": 286.52,
    "number_of_stops": 7,
    "start_fuel_gallons": 50.0,
    "vehicle_range_miles": 500,
    "miles_per_gallon": 10,
    "stations_considered": 259
  },
  "external_api_calls": {"routing": 1, "geocoding": 0},
  "elapsed_ms": 412.3,
  "map_url": "http://127.0.0.1:8000/api/route/map/?start=New+York%2C+NY&finish=Los+Angeles%2C+CA"
}
```

Errors:

| Status | When |
|--------|------|
| `400`  | Invalid input, a location outside the USA, or an address that can't be geocoded |
| `422`  | No feasible fuel plan, e.g. a gap of more than 500 miles with no station |
| `502`  | The routing provider failed |

### `GET /api/route/map/`

Takes the same query parameters and returns an HTML page with a Leaflet map: the route, numbered fuel stops, and a cost breakdown. It reuses the cached route, so it makes no extra routing call.

A Postman collection is in `postman_collection.json`.

## How it works

1. **Geocoding.** Inputs like `"City, ST"` and `"lat,lng"` are resolved offline from a bundled table of about 39.5k US city centroids (`routing/data/us_city_coords.csv`, built from zip-code centroids by `scripts/build_city_coords.py`). Only free-text addresses go to Nominatim.
2. **Routing.** One OSRM request (`overview=full`, GeoJSON). Results are cached by coordinates.
3. **Stations on the route.** The polyline is densified to about 1-mile spacing and put into a KD-tree in 3D unit-sphere coordinates. Each station inside the route's bounding box is matched to its nearest route point. That gives a **mile marker** and an **off-route distance**, and stations more than `STATION_SEARCH_RADIUS_MILES` (default 10) away are dropped.
4. **Optimisation.** An exact dynamic program over `(station, fuel-origin)` states. It relies on the classic "fill or not to fill" property: at each stop the optimal plan either fills the tank (when the next stop is pricier) or buys just enough to reach the next stop or the destination. A small per-stop penalty (`STOP_PENALTY_USD`, default $5) stops the plan from pulling over for 1–2 gallons just to save a few cents. With the penalty set to 0, it matches the textbook optimal greedy algorithm; a randomised test checks this.
5. **Station data.** Loaded once into SQLite by the management command, then into an in-memory index the first time a request needs it. Canadian rows are skipped. When an OPIS ID appears more than once, the lowest price is kept.

## Assumptions

- The vehicle leaves with a full tank unless you pass `start_fuel_gallons`. `total_fuel_cost` is the cost of fuel **bought along the route**. With `start_fuel_gallons=0`, the first stop must be within the search radius of the start.
- The CSV has no coordinates, so stations are placed at their city's centroid. That's why the corridor is 10 miles wide.
- Off-route detour distance is reported but not added to the trip distance.

## Configuration (env vars)

- `OSRM_BASE_URL` (default: public demo server)
- `NOMINATIM_URL`
- `STATION_SEARCH_RADIUS_MILES`
- `STOP_PENALTY_USD`
- `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`

## Tests

```bash
coverage run manage.py test && coverage report
```

51 tests, 100% line coverage. External HTTP calls are mocked.
