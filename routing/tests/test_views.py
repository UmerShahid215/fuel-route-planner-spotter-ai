from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from routing.services import planner, routing_client
from routing.services.station_index import reset_station_index

from .helpers import make_station, osrm_payload, straight_line

START = "32.0,-102.0"
FINISH = "32.0,-90.0"


def osrm_get(distance=700.0):
    resp = mock.Mock()
    resp.json.return_value = osrm_payload(straight_line(32.0, -102.0, -90.0).tolist(), distance, 36000)
    return mock.Mock(return_value=resp)


class RouteApiTests(TestCase):
    def setUp(self):
        cache.clear()
        reset_station_index()
        make_station(1, 32.0, -101.0, "3.5000", city="West")
        make_station(2, 32.02, -96.0, "2.9000", city="Middle", name="CHEAP STOP")
        make_station(3, 32.0, -93.0, "3.9000", city="East")
        make_station(4, 35.0, -96.0, "1.0000", city="Far Away")

    def tearDown(self):
        reset_station_index()

    def get(self, **params):
        return self.client.get(reverse("route-plan"), {"start": START, "finish": FINISH, **params})

    def test_plans_route_with_single_routing_call(self):
        with mock.patch.object(routing_client.requests, "get", osrm_get()) as get:
            resp = self.get(start_fuel_gallons=10)
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(get.call_count, 1)
        self.assertEqual(data["external_api_calls"], {"routing": 1, "geocoding": 0})
        self.assertEqual(data["route"]["distance_miles"], 700.0)
        self.assertEqual(data["route"]["geometry"]["type"], "LineString")
        names = [s["name"] for s in data["fuel_stops"]]
        self.assertIn("CHEAP STOP", names)
        self.assertNotIn("Station 4", names)
        summary = data["summary"]
        self.assertAlmostEqual(summary["total_gallons_purchased"] + 10, summary["total_gallons_used"], places=1)
        self.assertAlmostEqual(summary["total_fuel_cost"], sum(s["cost"] for s in data["fuel_stops"]), places=1)
        self.assertIn("/api/route/map/?start=", data["map_url"])
        self.assertIn("start_fuel_gallons=10", data["map_url"])

    def test_repeat_request_uses_cache(self):
        with mock.patch.object(routing_client.requests, "get", osrm_get()) as get:
            self.get()
            data = self.get().json()
        self.assertEqual(get.call_count, 1)
        self.assertEqual(data["external_api_calls"]["routing"], 0)

    def test_post_and_exclude_geometry(self):
        with mock.patch.object(routing_client.requests, "get", osrm_get()):
            resp = self.client.post(
                reverse("route-plan"),
                {"start": START, "finish": FINISH, "include_geometry": False},
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("geometry", resp.json()["route"])

    def test_full_tank_short_trip_needs_no_stops(self):
        with mock.patch.object(routing_client.requests, "get", osrm_get(distance=400)):
            data = self.get().json()
        self.assertEqual(data["fuel_stops"], [])
        self.assertEqual(data["summary"]["total_fuel_cost"], 0)

    def test_validation_errors(self):
        self.assertEqual(self.client.get(reverse("route-plan")).status_code, 400)
        resp = self.get(start_fuel_gallons=80)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("start_fuel_gallons", resp.json())

    def test_location_outside_usa(self):
        resp = self.get(start="51.5,-0.12")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("outside the USA", resp.json()["detail"])

    def test_infeasible_route(self):
        with mock.patch.object(routing_client.requests, "get", osrm_get(distance=1500)):
            resp = self.get(start_fuel_gallons=0)
        self.assertEqual(resp.status_code, 422)

    def test_routing_failure(self):
        bad = mock.Mock()
        bad.json.return_value = {"code": "NoRoute", "routes": []}
        with mock.patch.object(routing_client.requests, "get", return_value=bad):
            resp = self.get()
        self.assertEqual(resp.status_code, 502)

    @override_settings(FUEL_ROUTE={**planner.settings.FUEL_ROUTE, "STATION_SEARCH_RADIUS_MILES": 1.0})
    def test_respects_search_radius_setting(self):
        with mock.patch.object(routing_client.requests, "get", osrm_get()):
            data = self.get(start_fuel_gallons=50).json()
        self.assertEqual(data["summary"]["stations_considered"], 2)


class RouteMapViewTests(TestCase):
    def setUp(self):
        cache.clear()
        reset_station_index()
        make_station(1, 32.0, -96.0, "3.0000", name="MAP STOP")

    def tearDown(self):
        reset_station_index()

    def test_renders_map(self):
        with mock.patch.object(routing_client.requests, "get", osrm_get()):
            resp = self.client.get(reverse("route-map"), {"start": START, "finish": FINISH, "start_fuel_gallons": 40})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "leaflet")
        self.assertContains(resp, "MAP STOP")
        self.assertContains(resp, 'id="plan-data"')

    def test_invalid_params(self):
        resp = self.client.get(reverse("route-map"))
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "Could not plan route", status_code=400)

    def test_planning_error(self):
        resp = self.client.get(reverse("route-map"), {"start": "48.85,2.35", "finish": FINISH})
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "outside the USA", status_code=400)


class FreeTextGeocodingTests(TestCase):
    def setUp(self):
        cache.clear()
        reset_station_index()

    def tearDown(self):
        reset_station_index()

    def test_nominatim_calls_are_counted_and_cached(self):
        nominatim = mock.Mock()
        nominatim.json.return_value = [{"lat": "32.0", "lon": "-102.0", "display_name": "Somewhere, TX"}]
        osrm = osrm_get(distance=300).return_value

        def dispatch(url, **kwargs):
            return nominatim if "nominatim" in url else osrm

        with mock.patch("requests.get", side_effect=dispatch) as get:
            first = self.client.get(reverse("route-plan"), {"start": "100 Main Street Midland", "finish": FINISH}).json()
            second = self.client.get(reverse("route-plan"), {"start": "100 Main Street Midland", "finish": FINISH}).json()
        self.assertEqual(first["external_api_calls"], {"routing": 1, "geocoding": 1})
        self.assertEqual(second["external_api_calls"], {"routing": 0, "geocoding": 0})
        self.assertEqual(get.call_count, 2)
        self.assertEqual(first["start"]["source"], "nominatim")
