"""Explainable insertion-based greedy heuristic with hard feasibility checks."""
from __future__ import annotations
from typing import Dict, Iterable, List, Optional, Tuple

from .models import Delivery, fmt_time, EPS
from .plan import Plan
from .schedule import Env, Route, Stop, evaluate_route

CHANGE_PENALTY = 5.0   # minutes-equivalent cost for moving a pending delivery to another vehicle


def order_key(d: Delivery):
    return (-d.priority, d.tw_end, d.tw_start, d.id)


def order_key_alt(d: Delivery):   # fallback ordering: earliest window opening first
    return (-d.priority, d.tw_start, d.tw_end, d.id)


def new_plan(env: Env, start_now: float = None) -> Plan:
    routes = {v.id: Route(v.id, env.depot, v.start_time, []) for v in env.vehicles.values()}
    return Plan(routes=routes, now=min(v.start_time for v in env.vehicles.values()) if start_now is None else start_now)


def _next_reload_id(plan: Plan) -> str:
    """Generate a unique reload ID for this plan."""
    plan.reload_seq += 1
    return f"RELOAD:{plan.reload_seq}"


def _candidates(route: Route, d: Delivery, rf: Optional[str], plan: Plan,
                env: Optional[Env] = None) -> Iterable[Tuple[List[Stop], Stop]]:
    stops, lc = route.stops, route.locked_count()
    S = Stop(d.id, "deliver", d.location)
    n = len(stops)

    # Check if this urgent delivery needs a reload (parcel at depot, vehicle already departed)
    needs_reload = (d.priority == 1 and d.release_time > 0 and rf is None
                    and env is not None and _vehicle_departed(route, plan))

    if rf is None and not needs_reload:
        for p in range(lc, n + 1):
            yield stops[:p] + [S] + stops[p:], S
        return
    if rf is None and needs_reload:
        # Vehicle has departed; urgent parcel is at the depot.
        # Insert reload stop (return to depot) then deliver.
        # Also try without reload if vehicle origin is depot (hasn't departed yet)
        depot = env.depot
        # Check if there's already a reload in the route we can place after
        existing_reload = next((i for i, s in enumerate(stops) if s.kind == "reload"), None)
        if existing_reload is not None:
            # Place delivery after the existing reload stop (which returns to depot)
            for p in range(max(lc, existing_reload + 1), n + 1):
                yield stops[:p] + [S] + stops[p:], S
        else:
            rl = Stop(_next_reload_id(plan), "reload", depot, ready_at=d.release_time)
            for p1 in range(lc, n + 1):
                base = stops[:p1] + [rl] + stops[p1:]
                for p2 in range(p1 + 1, len(base) + 1):
                    yield base[:p2] + [S] + base[p2:], S
        return
    # Recovery from failed vehicle
    idx = next((i for i, s in enumerate(stops) if s.kind == "pickup" and s.recover_from == rf), None)
    if idx is not None:
        for p in range(max(lc, idx + 1), n + 1):
            yield stops[:p] + [S] + stops[p:], S
    else:
        f = plan.failures[rf]
        pk = Stop(f"PICKUP:{rf}", "pickup", f["location"], rf, ready_at=f["time"])
        for p1 in range(lc, n + 1):
            base = stops[:p1] + [pk] + stops[p1:]
            for p2 in range(p1 + 1, len(base) + 1):
                yield base[:p2] + [S] + base[p2:], S


def _vehicle_departed(route: Route, plan: Plan) -> bool:
    """Has this vehicle already departed the depot?  True if it has locked stops or completed history."""
    if plan.history.get(route.vehicle_id):
        return True
    if route.locked_count() > 0:
        return True
    return False


def prove_infeasible(d: Delivery, env: Env, plan: Plan, vids: List[str]) -> Optional[str]:
    """Return a reason only if infeasibility is *provable* from simple lower bounds."""
    if not vids:
        return "No vehicle is available (all failed)."
    if d.tw_end < d.release_time - EPS:
        return f"Window closes ({fmt_time(d.tw_end)}) before the order exists ({fmt_time(d.release_time)})."
    cap = max(env.vehicles[v].capacity for v in vids)
    if d.weight > cap + EPS:
        return f"Weight {d.weight:g} exceeds the largest available vehicle capacity {cap:g}."
    rf = plan.recover.get(d.id)
    best = float("inf")
    for v in vids:
        r = plan.routes[v]
        t = max(r.origin_time, d.release_time)
        if rf:
            f = plan.failures[rf]
            t = max(t + env.travel.base(r.origin, f["location"]), f["time"]) + env.transfer_minutes
            t += env.travel.base(f["location"], d.location)
        elif d.priority == 1 and d.release_time > 0 and _vehicle_departed(r, plan):
            # Urgent parcel at depot: vehicle must return to depot first
            t_depot = t + env.travel.base(r.origin, env.depot)
            t_depot = max(t_depot, d.release_time) + env.transfer_minutes
            t = t_depot + env.travel.base(env.depot, d.location)
        else:
            t += env.travel.base(r.origin, d.location)
        best = min(best, max(t, d.tw_start))
    if best > d.tw_end + EPS:
        return (f"Provably infeasible: earliest conceivable service {fmt_time(best)} "
                f"is after the deadline {fmt_time(d.tw_end)} even with an empty route.")
    return None


def insert_deliveries(plan: Plan, env: Env, pool: List[str], prefer: Dict[str, str] = None,
                      key=order_key) -> None:
    """Greedy insertion. Mutates plan.routes / plan.unassigned. Every pool item ends up in exactly one."""
    prefer = prefer or {}
    vids = [v for v in sorted(plan.routes) if v not in plan.failures]
    for did in sorted(pool, key=lambda x: key(env.deliveries[x])):
        d = env.deliveries[did]
        rf = plan.recover.get(did)
        plan.unassigned.pop(did, None)
        best, best_v = None, None
        diag = {"capacity": 0, "own_window": 0, "downstream_window": 0, "precedence": 0, "tried": 0}
        base_cost = {v: evaluate_route(plan.routes[v], env, plan.recover).travel for v in vids}
        for v in vids:
            route = plan.routes[v]
            if rf is not None and rf == v:
                continue
            for cand, S in _candidates(route, d, rf, plan, env):
                diag["tried"] += 1
                r2 = Route(v, route.origin, route.origin_time, cand)
                ev = evaluate_route(r2, env, plan.recover)
                if not ev.feasible:
                    vi = ev.violations[0]
                    if vi["type"] == "window":
                        mine = cand[vi["index"]] is S
                        diag["own_window" if mine else "downstream_window"] += 1
                    else:
                        diag[vi["type"]] = diag.get(vi["type"], 0) + 1
                    continue
                cost = ev.travel - base_cost[v]
                if prefer.get(did) not in (None, v):
                    cost += CHANGE_PENALTY
                score = (round(cost, 6), -round(ev.min_slack, 6), v)
                if best is None or score < best[0]:
                    best, best_v = (score, cand, ev), v
        if best is not None:
            r = plan.routes[best_v]
            plan.routes[best_v] = Route(best_v, r.origin, r.origin_time, best[1])
        else:
            proof = prove_infeasible(d, env, plan, vids)
            if proof:
                plan.unassigned[did] = {"reason": proof, "proven": True, "category": "proven_infeasible"}
            else:
                plan.unassigned[did] = {
                    "reason": (f"No feasible insertion found ({diag['tried']} positions tried: "
                               f"{diag['capacity']} blocked by capacity, {diag['own_window']} missed this window, "
                               f"{diag['downstream_window']} would make other deliveries late). "
                               "Not proven impossible - the greedy heuristic may simply have failed to place it."),
                    "proven": False, "category": "heuristic_failure"}


def build_initial_plan(env: Env, key=order_key) -> Plan:
    plan = new_plan(env)
    insert_deliveries(plan, env, list(env.deliveries), key=key)
    # Apply post-pass optimization
    post_pass(plan, env)
    return plan


def post_pass(plan: Plan, env: Env) -> int:
    """Try relocate (move a stop to a better position) and 2-opt (reverse a segment).
    Only keep changes that don't introduce violations. Returns number of improvements."""
    from .validator import validate_plan
    vids = [v for v in sorted(plan.routes) if v not in plan.failures]
    improved = 0

    # 1. Relocate: try moving each pending deliver stop to a better position on same route
    for vid in vids:
        r = plan.routes[vid]
        lc = r.locked_count()
        base_ev = evaluate_route(r, env, plan.recover, full=True)
        if not base_ev.feasible:
            continue
        for i in range(lc, len(r.stops)):
            s = r.stops[i]
            if s.locked or s.kind != "deliver":
                continue
            for j in range(lc, len(r.stops) + 1):
                if j == i or j == i + 1:
                    continue
                trial = r.stops[:i] + r.stops[i + 1:]
                ins_j = j if j < i else j - 1
                trial = trial[:ins_j] + [s] + trial[ins_j:]
                trial_r = Route(vid, r.origin, r.origin_time, trial)
                trial_ev = evaluate_route(trial_r, env, plan.recover, full=True)
                if trial_ev.feasible and trial_ev.travel < base_ev.travel - 0.1:
                    plan.routes[vid] = trial_r
                    r = trial_r
                    base_ev = trial_ev
                    improved += 1
                    break

    # 2. 2-opt: try reversing segments on each route
    for vid in vids:
        r = plan.routes[vid]
        lc = r.locked_count()
        base_ev = evaluate_route(r, env, plan.recover, full=True)
        if not base_ev.feasible or len(r.stops) - lc < 3:
            continue
        for i in range(lc, len(r.stops) - 1):
            for j in range(i + 2, min(i + 5, len(r.stops) + 1)):  # limit segment length
                trial = r.stops[:i] + list(reversed(r.stops[i:j])) + r.stops[j:]
                trial_r = Route(vid, r.origin, r.origin_time, trial)
                trial_ev = evaluate_route(trial_r, env, plan.recover, full=True)
                if trial_ev.feasible and trial_ev.travel < base_ev.travel - 0.1:
                    plan.routes[vid] = trial_r
                    r = trial_r
                    base_ev = trial_ev
                    improved += 1

    return improved
