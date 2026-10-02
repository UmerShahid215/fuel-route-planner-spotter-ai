import numpy as np
from django.test import SimpleTestCase, TestCase

from routing.services.geo import densify
from routing.services.station_index import Station, StationIndex, get_station_index, reset_station_index

from .helpers import make_station, straight_line


def st(i, lat, lng, price=3.0):
    return Station(i, f"S{i}", "addr", "City", "TX", price, lat, lng)


class StationIndexTests(SimpleTestCase):
    def test_along_route_filters_by_radius_and_orders_by_mile(self):
        points, miles = densify(straight_line(32.0, -100.0, -96.0), 1.0)
        index = StationIndex([st(1, 32.05, -97.0), st(2, 32.0, -99.5), st(3, 33.0, -98.0), st(4, 40.0, -80.0)])
        hits = index.along_route(points, miles, radius_miles=10)
        self.assertEqual([h.station.opis_id for h in hits], [2, 1])
        self.assertLess(hits[0].mile, hits[1].mile)
        self.assertAlmostEqual(hits[1].off_route_miles, 3.45, delta=0.2)
        self.assertEqual(hits[0].price, 3.0)

    def test_empty_inputs(self):
        points, miles = densify(straight_line(32.0, -100.0, -96.0), 1.0)
        self.assertEqual(StationIndex([]).along_route(points, miles, 10), [])
        self.assertEqual(StationIndex([st(1, 32.0, -99.0)]).along_route(np.empty((0, 2)), np.empty(0), 10), [])
        self.assertEqual(StationIndex([st(1, 45.0, -70.0)]).along_route(points, miles, 10), [])


class StationIndexDbTests(TestCase):
    def tearDown(self):
        reset_station_index()

    def test_loaded_lazily_from_db_and_cached(self):
        reset_station_index()
        make_station(1, 32.0, -99.0, "3.1990")
        index = get_station_index()
        self.assertIs(index, get_station_index())
        self.assertEqual(index.stations[0].price, 3.199)
        reset_station_index()
        self.assertIsNot(index, get_station_index())
