import numpy as np
from django.test import SimpleTestCase

from routing.services.geo import chord_to_miles, densify, haversine_miles, miles_to_chord, to_unit_xyz


class GeoTests(SimpleTestCase):
    def test_haversine_known_distance(self):
        self.assertAlmostEqual(float(haversine_miles(40.7128, -74.0060, 34.0522, -118.2437)), 2445, delta=5)

    def test_chord_roundtrip(self):
        self.assertAlmostEqual(float(chord_to_miles(miles_to_chord(42.0))), 42.0, places=6)

    def test_unit_xyz_is_normalised(self):
        xyz = to_unit_xyz(np.array([10.0, -45.0]), np.array([20.0, 170.0]))
        np.testing.assert_allclose(np.linalg.norm(xyz, axis=1), 1.0)

    def test_densify_limits_step_and_preserves_length(self):
        line = np.array([[35.0, -100.0], [35.0, -99.0], [35.0, -99.0], [36.0, -99.0]])
        points, miles = densify(line, step_miles=1.0)
        gaps = haversine_miles(points[:-1, 0], points[:-1, 1], points[1:, 0], points[1:, 1])
        self.assertLessEqual(gaps.max(), 1.0 + 1e-6)
        total = haversine_miles(line[:-1, 0], line[:-1, 1], line[1:, 0], line[1:, 1]).sum()
        self.assertAlmostEqual(miles[-1], total, places=6)
        np.testing.assert_array_equal(points[-1], line[-1])
        self.assertTrue(np.all(np.diff(miles) >= 0))

    def test_densify_single_point(self):
        points, miles = densify([[35.0, -100.0]])
        self.assertEqual(len(points), 1)
        self.assertEqual(miles.tolist(), [0.0])
