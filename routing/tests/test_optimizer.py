import random

from django.test import SimpleTestCase

from routing.services.optimizer import InfeasibleRoute, plan_fuel_stops, thin_candidates

from .helpers import cand


def reference_greedy(cands, total, cap, mpg, fuel):
    """Textbook optimal greedy (no stop penalty), used as an oracle."""
    cands = sorted(cands, key=lambda c: c.mile)
    cost, i = 0.0, None
    while True:
        here = cands[i].mile if i is not None else 0.0
        price = cands[i].price if i is not None else float("inf")
        limit = here + (cap if i is not None else fuel)
        ahead = [k for k in range(0 if i is None else i + 1, len(cands)) if cands[k].mile <= limit]
        cheaper = next((k for k in ahead if cands[k].price < price), None)
        if cheaper is None and total - here <= (cap if i is not None else fuel):
            buy = max(total - here - fuel, 0)
            return cost + buy / mpg * price if buy else cost
        if cheaper is not None:
            target = cheaper
            buy = max(cands[cheaper].mile - here - fuel, 0)
        else:
            if not ahead:
                return None
            target = min(ahead, key=lambda k: (cands[k].price, -cands[k].mile))
            buy = cap - fuel
        if buy:
            cost += buy / mpg * price
        fuel = fuel + buy - (cands[target].mile - here)
        i = target


class OptimizerTests(SimpleTestCase):
    def test_no_stop_needed_when_start_fuel_covers_trip(self):
        plan = plan_fuel_stops([cand(10, 3.0)], total_miles=300, range_miles=500, mpg=10, start_fuel_miles=500)
        self.assertEqual(plan.stops, [])
        self.assertEqual(plan.total_cost, 0)

    def test_buys_only_what_is_needed_to_finish(self):
        plan = plan_fuel_stops([cand(100, 3.0)], total_miles=600, range_miles=500, mpg=10, start_fuel_miles=500)
        self.assertEqual(len(plan.stops), 1)
        self.assertAlmostEqual(plan.stops[0].gallons, 10.0)
        self.assertAlmostEqual(plan.total_cost, 30.0)
        self.assertAlmostEqual(plan.stops[0].fuel_on_arrival_gallons, 40.0)

    def test_prefers_cheaper_station_within_range(self):
        stations = [cand(100, 4.0), cand(400, 2.0)]
        plan = plan_fuel_stops(stations, total_miles=800, range_miles=500, mpg=10, start_fuel_miles=500)
        self.assertEqual([s.candidate.mile for s in plan.stops], [400])
        self.assertAlmostEqual(plan.total_cost, 30 * 2.0)

    def test_fills_up_at_cheap_station_before_expensive_stretch(self):
        stations = [cand(0, 2.0), cand(300, 5.0), cand(600, 5.0)]
        plan = plan_fuel_stops(stations, total_miles=900, range_miles=500, mpg=10, start_fuel_miles=0)
        self.assertAlmostEqual(plan.stops[0].gallons, 50.0)
        self.assertAlmostEqual(plan.total_gallons, 90.0)
        self.assertAlmostEqual(plan.total_cost, 50 * 2.0 + 40 * 5.0)

    def test_start_grace_allows_empty_tank_start(self):
        plan = plan_fuel_stops([cand(5, 3.0)], total_miles=200, range_miles=500, mpg=10, start_fuel_miles=0, start_grace_miles=10)
        self.assertAlmostEqual(plan.total_gallons, 19.5)

    def test_unreachable_first_station(self):
        with self.assertRaisesMessage(InfeasibleRoute, "first"):
            plan_fuel_stops([cand(50, 3.0)], total_miles=600, range_miles=500, mpg=10, start_fuel_miles=0, start_grace_miles=10)

    def test_no_stations_at_all(self):
        with self.assertRaises(InfeasibleRoute):
            plan_fuel_stops([], total_miles=600, range_miles=500, mpg=10, start_fuel_miles=500)

    def test_gap_larger_than_range(self):
        with self.assertRaisesMessage(InfeasibleRoute, "Gap of more than 500 miles"):
            plan_fuel_stops([cand(100, 3.0)], total_miles=1200, range_miles=500, mpg=10, start_fuel_miles=500)

    def test_stop_penalty_reduces_number_of_stops(self):
        stations = [cand(m, 3.0 + (0.001 if m % 2 else 0)) for m in range(20, 1000, 20)]
        cheap = plan_fuel_stops(stations, 1000, 500, 10, 500, stop_penalty=0)
        fewer = plan_fuel_stops(stations, 1000, 500, 10, 500, stop_penalty=10)
        self.assertLessEqual(len(fewer.stops), len(cheap.stops))
        self.assertLessEqual(len(fewer.stops), 2)

    def test_fuel_balance_holds(self):
        stations = [cand(m, 3 + (m % 7) / 10) for m in range(0, 2500, 37)]
        plan = plan_fuel_stops(stations, 2500, 500, 10, 300, stop_penalty=5)
        self.assertAlmostEqual(plan.total_gallons + 30, 250, places=6)

    def test_matches_reference_greedy_without_penalty(self):
        rng = random.Random(7)
        for _ in range(200):
            total = rng.uniform(300, 2500)
            stations = [cand(rng.uniform(0, total), round(rng.uniform(2.5, 4.5), 3)) for _ in range(rng.randint(5, 60))]
            start = rng.choice([0, 120, 500])
            stations.append(cand(0, 3.5))
            expected = reference_greedy(thin_candidates(stations, total), total, 500, 10, start)
            try:
                got = plan_fuel_stops(stations, total, 500, 10, start).total_cost
            except InfeasibleRoute:
                got = None
            if expected is None:
                self.assertIsNone(got)
            else:
                self.assertAlmostEqual(got, expected, places=6)

    def test_thin_candidates_keeps_cheapest_in_cluster(self):
        kept = thin_candidates([cand(10, 3.5), cand(10.2, 3.1), cand(30, 3.0), cand(-1, 1.0), cand(99, 1.0)], 50)
        self.assertEqual([(c.mile, c.price) for c in kept], [(10.2, 3.1), (30, 3.0)])
