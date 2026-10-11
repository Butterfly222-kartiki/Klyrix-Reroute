"""Plan data structures and route evaluation (arrival, waiting, capacity, windows)."""
from __future__ import annotations
import copy
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .models import EPS, Delivery, Scenario, Vehicle, Closure
from .travel import TravelModel


@dataclass
class Stop:
    id: str                      # delivery id, "PICKUP:<failed vehicle>", or "RELOAD:<seq>"
    kind: str                    # 'deliver' | 'pickup' | 'reload'
    location: str
    recover_from: Optional[str] = None   # pickup: failed vehicle whose cargo is collected
    ready_at: float = 0.0                # pickup cannot start before this (failure time)
    locked: bool = False                 # committed (already en route / in service)
    service_time: Optional[float] = None # override service duration (reload uses transfer_minutes)

    def to_dict(self):
        return dict(self.__dict__)


@dataclass
class Route:
    vehicle_id: str
    origin: str
    origin_time: float
    stops: List[Stop] = field(default_factory=list)

    def locked_count(self) -> int:
        n = 0
        for s in self.stops:
            if s.locked:
                n += 1
            else:
                break
        return n

    def copy(self) -> "Route":
        return copy.deepcopy(self)


@dataclass
class Env:
    """Everything the planner needs to know about the world *right now*."""
    depot: str
    vehicles: Dict[str, Vehicle]
    deliveries: Dict[str, Delivery]
    matrix: Dict[str, Dict[str, float]]
    closures: List[Closure]
    transfer_minutes: float
    locations: Dict[str, dict]
    travel: TravelModel = None

    def __post_init__(self):
        if self.travel is None:
            self.travel = TravelModel(self.matrix, self.closures)

    @classmethod
    def from_scenario(cls, s: Scenario) -> "Env":
        return cls(s.depot, {v.id: v for v in s.vehicles}, {d.id: d for d in s.deliveries},
                   s.matrix, list(s.closures), s.transfer_minutes, s.locations)

    def evolve(self, closures=None, add_deliveries=()) -> "Env":
        cl = list(self.closures) if closures is None else closures
        dm = dict(self.deliveries)
        for d in add_deliveries:
            dm[d.id] = d
        return Env(self.depot, self.vehicles, dm, self.matrix, cl, self.transfer_minutes,
                   self.locations, self.travel.with_closures(cl) if closures is not None else self.travel)

    def remove_closure(self, closure_id: str) -> "Env":
        """Remove a closure by id, returning a new Env."""
        cl = [c for c in self.closures if c.id != closure_id]
        return Env(self.depot, self.vehicles, self.deliveries, self.matrix, cl,
                   self.transfer_minutes, self.locations, self.travel.with_closures(cl))

    def expire_closures(self, t: float) -> "Env":
        """Remove closures whose end time is <= t, returning a new Env."""
        cl = [c for c in self.closures if c.end > t]
        if len(cl) == len(self.closures):
            return self
        return Env(self.depot, self.vehicles, self.deliveries, self.matrix, cl,
                   self.transfer_minutes, self.locations, self.travel.with_closures(cl))


@dataclass
class RouteEval:
    feasible: bool
    violations: List[dict]
    rows: List[dict]
    travel: float
    wait: float
    end_time: float
    initial_load: float
    peak_load: float
    min_slack: float


def evaluate_route(route: Route, env: Env, recover: Dict[str, str], full: bool = False) -> RouteEval:
    """Compute schedule for the route's pending stops. If full=False stops at first violation."""
    veh = env.vehicles[route.vehicle_id]
    tm = env.travel
    stops = route.stops
    viol: List[dict] = []
    rows: List[dict] = []
    # If there's a reload stop, the vehicle only loads deliveries before the first reload at departure
    first_reload = next((i for i, s in enumerate(stops) if s.kind == "reload"), None)
    pre_reload = stops[:first_reload] if first_reload is not None else stops
    init = sum(env.deliveries[s.id].weight for s in pre_reload if s.kind == "deliver" and s.id not in recover)
    load, peak = init, init
    if init > veh.capacity + EPS:
        viol.append({"type": "capacity", "index": -1, "msg": f"Departure load {init:g} > capacity {veh.capacity:g}"})
        if not full:
            return RouteEval(False, viol, rows, 0, 0, route.origin_time, init, init, 0)
    t, loc, trav, wait, slack = route.origin_time, route.origin, 0.0, 0.0, float("inf")
    picked = set()
    for i, s in enumerate(stops):
        tt = tm.time(loc, s.location, t)
        if tt == float("inf"):
            viol.append({"type": "unreachable", "index": i, "msg": f"Location {s.location} is unreachable from {loc}"})
            if not full:
                return RouteEval(False, viol, rows, trav, wait, t, init, peak, slack)
        arr = t + tt
        trav += tt
        if s.kind == "pickup":
            start = max(arr, s.ready_at)
            w = start - arr
            pw = sum(env.deliveries[x.id].weight for x in stops if x.kind == "deliver" and recover.get(x.id) == s.recover_from)
            load += pw
            peak = max(peak, load)
            if load > veh.capacity + EPS:
                viol.append({"type": "capacity", "index": i, "msg": f"Load {load:g} > capacity after pickup"})
            end = start + env.transfer_minutes
            picked.add(s.recover_from)
            row = dict(stop_id=s.id, kind="pickup", location=s.location, arrival=arr, wait=w, start=start,
                       depart=end, load_after=load, leg=tt, locked=s.locked, tw_start=None, tw_end=None, slack=None)
        elif s.kind == "reload":
            start = max(arr, s.ready_at)
            w = start - arr
            svc = s.service_time if s.service_time is not None else env.transfer_minutes
            end = start + svc
            # After reload, load is reset to what's needed for remaining deliveries (after this stop)
            remaining = sum(env.deliveries[x.id].weight for x in stops[i+1:] if x.kind == "deliver" and x.id not in recover)
            # Plus weight for pickups still pending
            for x in stops[i+1:]:
                if x.kind == "pickup":
                    remaining += sum(env.deliveries[y.id].weight for y in stops[i+1:] if y.kind == "deliver" and recover.get(y.id) == x.recover_from)
            load = remaining
            peak = max(peak, load)
            if load > veh.capacity + EPS:
                viol.append({"type": "capacity", "index": i, "msg": f"Load {load:g} > capacity after reload"})
            row = dict(stop_id=s.id, kind="reload", location=s.location, arrival=arr, wait=w, start=start,
                       depart=end, load_after=load, leg=tt, locked=s.locked, tw_start=None, tw_end=None, slack=None)
        else:
            d = env.deliveries[s.id]
            rf = recover.get(s.id)
            if rf and rf not in picked:
                viol.append({"type": "precedence", "index": i, "msg": f"{d.id} scheduled before cargo pickup from {rf}"})
            start = max(arr, d.tw_start, d.release_time)
            w = start - arr
            sl = d.tw_end - start
            if sl < -EPS:
                viol.append({"type": "window", "index": i, "msg": f"{d.id}: service start {start:.0f} after deadline {d.tw_end:.0f}"})
            slack = min(slack, sl)
            end = start + d.service
            load -= d.weight
            row = dict(stop_id=s.id, kind="deliver", location=s.location, arrival=arr, wait=w, start=start,
                       depart=end, load_after=load, leg=tt, locked=s.locked, tw_start=d.tw_start, tw_end=d.tw_end, slack=sl)
        wait += w
        rows.append(row)
        if viol and not full:
            return RouteEval(False, viol, rows, trav, wait, end, init, peak, slack)
        t, loc = end, s.location
    back = tm.time(loc, env.depot, t) if stops else 0.0
    if back == float("inf"):
        viol.append({"type": "unreachable", "index": len(stops) - 1, 
                     "msg": f"Cannot return to depot from {loc}"})
        if not full:
            return RouteEval(False, viol, rows, trav, wait, t, init, peak, slack)
        end_time = float("inf")
    else:
        trav += back
        end_time = t + back
    if end_time > veh.shift_end + EPS and stops:
        viol.append({"type": "shift_end", "index": len(stops) - 1,
                     "msg": f"Return to depot at {end_time:.0f} after shift end {veh.shift_end:.0f}"})
        if not full:
            return RouteEval(False, viol, rows, trav, wait, end_time, init, peak,
                             0.0 if slack == float("inf") else slack)
    return RouteEval(not viol, viol, rows, trav, wait, end_time, init, peak, 0.0 if slack == float("inf") else slack)
