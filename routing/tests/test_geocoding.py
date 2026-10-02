from unittest import mock

import requests
from django.test import SimpleTestCase

from routing.services import geocoding
from routing.services.geocoding import GeocodingError, geocode, in_usa, lookup_city, normalize_city


def fake_response(payload, status=200):
    resp = mock.Mock(status_code=status)
    resp.json.return_value = payload
    resp.raise_for_status.side_effect = None if status < 400 else requests.HTTPError("boom")
    return resp


class GeocodingTests(SimpleTestCase):
    def test_normalize_city(self):
        self.assertEqual(normalize_city("St. Louis"), normalize_city("Saint Louis"))
        self.assertEqual(normalize_city("De Forest"), normalize_city("DeForest"))
        self.assertEqual(normalize_city("Fort Worth"), "FTWORTH")

    def test_lookup_city(self):
        lat, lng = lookup_city("Chicago", "il")
        self.assertAlmostEqual(lat, 41.85, delta=0.3)
        self.assertAlmostEqual(lng, -87.68, delta=0.3)
        self.assertIsNone(lookup_city("Atlantis", "ZZ"))

    def test_in_usa(self):
        self.assertTrue(in_usa(39.0, -98.0))
        self.assertTrue(in_usa(61.2, -149.9))
        self.assertTrue(in_usa(21.3, -157.8))
        self.assertFalse(in_usa(51.5, -0.12))

    def test_coordinates(self):
        loc = geocode(" 39.7392, -104.9903 ")
        self.assertEqual((loc.lat, loc.lng, loc.source), (39.7392, -104.9903, "coordinates"))

    def test_coordinates_outside_usa(self):
        with self.assertRaisesMessage(GeocodingError, "outside the USA"):
            geocode("48.8566,2.3522")

    @mock.patch.object(geocoding.requests, "get")
    def test_city_state_resolved_locally(self, get):
        loc = geocode("Dallas, TX, USA")
        self.assertEqual(loc.source, "local")
        self.assertEqual(loc.label, "Dallas, TX")
        get.assert_not_called()

    def test_empty(self):
        with self.assertRaises(GeocodingError):
            geocode("  ")

    @mock.patch.object(geocoding.requests, "get")
    def test_nominatim_fallback(self, get):
        get.return_value = fake_response([{"lat": "38.8977", "lon": "-77.0365", "display_name": "White House"}])
        loc = geocode("1600 Pennsylvania Ave NW, Washington")
        self.assertEqual((loc.source, loc.label), ("nominatim", "White House"))
        self.assertEqual(get.call_args.kwargs["params"]["countrycodes"], "us")

    @mock.patch.object(geocoding.requests, "get")
    def test_nominatim_no_results(self, get):
        get.return_value = fake_response([])
        with self.assertRaisesMessage(GeocodingError, "Could not find"):
            geocode("zzzz nowhere")

    @mock.patch.object(geocoding.requests, "get")
    def test_nominatim_http_error(self, get):
        get.return_value = fake_response({}, status=500)
        with self.assertRaisesMessage(GeocodingError, "failed"):
            geocode("somewhere odd")

    @mock.patch.object(geocoding.requests, "get", side_effect=requests.ConnectionError)
    def test_nominatim_connection_error(self, _get):
        with self.assertRaises(GeocodingError):
            geocode("somewhere odd")
