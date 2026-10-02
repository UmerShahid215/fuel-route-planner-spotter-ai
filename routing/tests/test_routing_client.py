from unittest import mock

import requests
from django.test import SimpleTestCase

from routing.services import routing_client
from routing.services.geocoding import Location
from routing.services.routing_client import RoutingError, fetch_route

from .helpers import osrm_payload

A = Location(32.0, -100.0, "A", "coordinates")
B = Location(32.0, -95.0, "B", "coordinates")


class RoutingClientTests(SimpleTestCase):
    @mock.patch.object(routing_client.requests, "get")
    def test_parses_route(self, get):
        get.return_value.json.return_value = osrm_payload([(32.0, -100.0), (32.0, -95.0)], 300, 18000)
        route = fetch_route(A, B)
        self.assertEqual(route.latlon.tolist(), [[32.0, -100.0], [32.0, -95.0]])
        self.assertAlmostEqual(route.distance_miles, 300)
        self.assertEqual(route.duration_seconds, 18000)
        self.assertIn("-100.0,32.0;-95.0,32.0", get.call_args.args[0])

    @mock.patch.object(routing_client.requests, "get")
    def test_no_route(self, get):
        get.return_value.json.return_value = {"code": "NoRoute", "message": "Impossible route", "routes": []}
        with self.assertRaisesMessage(RoutingError, "Impossible route"):
            fetch_route(A, B)

    @mock.patch.object(routing_client.requests, "get", side_effect=requests.Timeout)
    def test_network_error(self, _get):
        with self.assertRaisesMessage(RoutingError, "unavailable"):
            fetch_route(A, B)
