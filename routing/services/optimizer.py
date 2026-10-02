import math
from dataclasses import dataclass, field

EPS = 1e-6
START, EMPTY = "start", "empty"


class InfeasibleRoute(Exception):
    pass


@dataclass
class FuelStop:
    candidate: object
    gallons: float
    cost: float
    fuel_on_arrival_gallons: float


@dataclass
class FuelPlan:
    stops: list = field(default_factory=list)

    @property
    def total_cost(self):
        return sum(s.cost for s in self.stops)

    @property
    def total_gallons(self):
        return sum(s.gallons for s in self.stops)


def thin_candidates(candidates, total_miles, cluster_miles=0.5):
    kept = []
    for c in sorted((c for c in candidates if 0 <= c.mile <= total_miles), key=lambda c: (c.mile, c.price)):
        if kept and c.mile - kept[-1].mile <= cluster_miles:
            if c.price < kept[-1].price:
                kept[-1] = c
            continue
        kept.append(c)
    return kept


def plan_fuel_stops(
    candidates, total_miles, range_miles, mpg, start_fuel_miles, start_grace_miles=0.0, stop_penalty=0.0
):
    """Exact DP: each stop either fills the tank or buys just enough to reach the next stop."""
    if total_miles <= start_fuel_miles + EPS:
        return FuelPlan()

    cands = thin_candidates(candidates, total_miles)
    pos = [c.mile for c in cands]
    price = [c.price for c in cands]
    n, cap = len(cands), range_miles
    entry_reach = max(start_fuel_miles, start_grace_miles)

    def fuel_at(i, origin):
        if origin == START:
            return max(start_fuel_miles - pos[i], 0.0)
        if origin == EMPTY:
            return 0.0
        return cap - (pos[i] - pos[origin])

    def origins(i):
        yield EMPTY
        if pos[i] <= entry_reach + EPS:
            yield START
        o = i - 1
        while o >= 0 and pos[i] - pos[o] <= cap + EPS:
            yield o
            o -= 1

    def purchase_cost(i, miles):
        return (miles / mpg) * price[i] + stop_penalty if miles > EPS else 0.0

    best, choice = [dict() for _ in range(n)], [dict() for _ in range(n)]
    for i in range(n - 1, -1, -1):
        for origin in origins(i):
            g = fuel_at(i, origin)
            top = (math.inf, None)
            to_end = total_miles - pos[i]
            if to_end <= cap + EPS:
                buy = max(to_end - g, 0.0)
                top = (purchase_cost(i, buy), (None, None, buy))
            j = i + 1
            while j < n and pos[j] - pos[i] <= cap + EPS:
                d = pos[j] - pos[i]
                if price[j] <= price[i]:
                    nxt, buy = (origin, 0.0) if g >= d - EPS else (EMPTY, d - g)
                else:
                    nxt, buy = i, cap - g
                val = purchase_cost(i, buy) + best[j].get(nxt, math.inf)
                if val < top[0]:
                    top = (val, (j, nxt, buy))
                j += 1
            best[i][origin], choice[i][origin] = top

    entries = [i for i in range(n) if pos[i] <= entry_reach + EPS]
    if not entries or min(best[i][START] for i in entries) == math.inf:
        raise InfeasibleRoute(_gap_message(pos, total_miles, cap, entry_reach))

    i = min(entries, key=lambda k: (best[k][START], pos[k]))
    origin, plan = START, FuelPlan()
    while True:
        j, nxt, bought = choice[i][origin]
        if bought > EPS:
            gallons = bought / mpg
            plan.stops.append(FuelStop(cands[i], gallons, gallons * price[i], fuel_at(i, origin) / mpg))
        if j is None:
            return plan
        i, origin = j, nxt


def _gap_message(pos, total_miles, cap, entry_reach):
    if not pos or pos[0] > entry_reach + EPS:
        return f"No fuel station reachable within the first {entry_reach:.0f} miles of the route."
    points = pos + [total_miles]
    for a, b in zip(points, points[1:]):
        if b - a > cap + EPS:
            return f"Gap of more than {cap:.0f} miles without a fuel station after mile {a:.0f}."
    return "No feasible fuelling plan found for this route."  # pragma: no cover
