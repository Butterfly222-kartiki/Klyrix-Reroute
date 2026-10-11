"""Independent constraint validator. Re-derives every timing from scratch; trusts nothing the planner says."""
from __future__ import annotations
from typing import Dict, List, Optional
from .models import EPS, fmt_time
from .plan import Plan
from .schedule import Env, Route


def _timeline(route: Route, env: Env, recover: Dict[str, str]) -> List[dict]:
    """Own implementation of the sequential schedule (deliberately separate from schedule.evaluate_route)."""
    t, loc, out = route.origin_time, route.origin, []
    for s in route.stops:
        tt = env.travel.time(loc, s.location, t)
        if tt == float("inf"):
            # Unreachable location
            return None  # Signal that timeline cannot be computed
        arr = t + tt
        if s.kind == "pickup":
            start, end = max(arr, s.ready_at), max(arr, s.ready_at) + env.transfer_minutes
        elif s.kind == "reload":
            svc = s.service_time if s.service_time is not None else env.transfer_minutes
            start = max(arr, s.ready_at)
            end = start + svc
        else:
            d = env.deliveries[s.id]
            start = max(arr, d.tw_start, d.release_time)
            end = start + d.service
        out.append(dict(stop=s, arrival=arr, start=start, depart=end))
        t, loc = end, s.location
    return out


def validate_plan(plan: Plan, env: Env, prior: Optional[Plan] = None, prior_env: Optional[Env] = None,
                  now: Optional[float] = None) -> dict:
    checks: List[dict] = []

    def chk(name, errs):
        checks.append({"name": name, "passed": not errs, "details": errs})

    # 1. accounting: every delivery exactly once
    seen: Dict[str, int] = {}
    for rows in plan.history.values():
        for r in rows:
            if r["kind"] == "deliver":
                seen[r["stop_id"]] = seen.get(r["stop_id"], 0) + 1
    for r in plan.routes.values():
        for s in r.stops:
            if s.kind == "deliver":
                seen[s.id] = seen.get(s.id, 0) + 1
    for did in plan.unassigned:
        seen[did] = seen.get(did, 0) + 1
    errs = [f"{d} appears {n}x" for d, n in seen.items() if n != 1]
    errs += [f"{d} is not accounted for" for d in env.deliveries if d not in seen]
    errs += [f"{d} is not a known delivery" for d in seen if d not in env.deliveries]
    chk("Delivery accounting (every order exactly once)", errs)

    timelines = {}
    unreachable_routes = []
    for vid, r in plan.routes.items():
        tl = _timeline(r, env, plan.recover)
        if tl is None:
            unreachable_routes.append(vid)
            timelines[vid] = []
        else:
            timelines[vid] = tl
    
    # Check for unreachable routes first
    if unreachable_routes:
        errs = [f"{vid}: route contains unreachable locations" for vid in unreachable_routes]
        chk("Reachability", errs)
        # Early exit if routes are unreachable
        return {"valid": False, "errors": [e for c in checks for e in c["details"]], "checks": checks}

    # 2. capacity at every point
    errs = []
    for vid, r in plan.routes.items():
        cap = env.vehicles[vid].capacity
        for row in plan.history.get(vid, []):
            if row["load_after"] > cap + EPS or row["load_after"] < -EPS:
                errs.append(f"{vid}: historical load {row['load_after']:g} outside [0,{cap:g}] at {row['stop_id']}")
        load = sum(env.deliveries[s.id].weight for s in r.stops if s.kind == "deliver" and s.id not in plan.recover)
        # If there's a reload, initial load only counts deliveries before the first reload
        first_reload_idx = next((i for i, s in enumerate(r.stops) if s.kind == "reload"), None)
        if first_reload_idx is not None:
            load = sum(env.deliveries[s.id].weight for s in r.stops[:first_reload_idx] if s.kind == "deliver" and s.id not in plan.recover)
        if load > cap + EPS:
            errs.append(f"{vid}: on-board load {load:g} > capacity {cap:g}")
        for idx_tl, tl in enumerate(timelines[vid]):
            s = tl["stop"]
            if s.kind == "pickup":
                load += sum(env.deliveries[x.id].weight for x in r.stops if x.kind == "deliver" and plan.recover.get(x.id) == s.recover_from)
            elif s.kind == "reload":
                # Load resets to what's needed for remaining deliveries
                remaining_stops = r.stops[idx_tl + 1:]
                remaining = sum(env.deliveries[x.id].weight for x in remaining_stops if x.kind == "deliver" and x.id not in plan.recover)
                for x in remaining_stops:
                    if x.kind == "pickup":
                        remaining += sum(env.deliveries[y.id].weight for y in remaining_stops if y.kind == "deliver" and plan.recover.get(y.id) == x.recover_from)
                load = remaining
            else:
                load -= env.deliveries[s.id].weight
            if load > cap + EPS:
                errs.append(f"{vid}: load {load:g} > capacity {cap:g} at {s.id}")
    chk("Vehicle capacity at every point along each route", errs)

    # 3. time windows + waiting
    errs = []
    for vid, tls in timelines.items():
        for tl in tls:
            s = tl["stop"]
            if s.kind != "deliver":
                continue
            d = env.deliveries[s.id]
            if tl["start"] > d.tw_end + EPS:
                errs.append(f"{d.id} on {vid}: service {fmt_time(tl['start'])} after deadline {fmt_time(d.tw_end)}")
            if tl["start"] < d.tw_start - EPS:
                errs.append(f"{d.id} on {vid}: service before window opens")
        for row in plan.history.get(vid, []):
            if row["kind"] == "deliver":
                d = env.deliveries[row["stop_id"]]
                if not (d.tw_start - EPS <= row["start"] <= d.tw_end + EPS):
                    errs.append(f"{d.id} (completed) outside window")
                if abs(row["wait"] - (row["start"] - row["arrival"])) > 1e-3:
                    errs.append(f"{d.id} (completed) wait inconsistent")
    chk("Delivery time windows and waiting time", errs)

    # 4. vehicle availability / failure
    errs = []
    for vid, f in plan.failures.items():
        if plan.routes[vid].stops:
            errs.append(f"Failed vehicle {vid} still has pending stops")
        for row in plan.history.get(vid, []):
            if row["depart"] > f["time"] + EPS:
                errs.append(f"Failed vehicle {vid} has work after failure time ({row['stop_id']})")
    for vid, tls in timelines.items():
        v = env.vehicles[vid]
        if tls and tls[0]["arrival"] < v.start_time - EPS:
            errs.append(f"{vid} moves before its start time")
        # shift_end: vehicle must return to depot by shift_end
        if tls:
            last_depart = tls[-1]["depart"]
            last_loc = tls[-1]["stop"].location
            ret_time = env.travel.time(last_loc, env.depot, last_depart)
            if ret_time == float("inf"):
                errs.append(f"{vid}: cannot return to depot from {last_loc}")
            else:
                ret = last_depart + ret_time
                if ret > v.shift_end + EPS:
                    errs.append(f"{vid}: returns to depot at {fmt_time(ret)} after shift end {fmt_time(v.shift_end)}")
    chk("Vehicle availability and failure handling", errs)

    # 5. chronology
    errs = []
    for vid, tls in timelines.items():
        last = max([r["depart"] for r in plan.history.get(vid, [])] or [plan.routes[vid].origin_time])
        for tl in tls:
            if tl["arrival"] < last - EPS:
                errs.append(f"{vid}: {tl['stop'].id} arrives before previous stop finishes")
            last = tl["depart"]
    chk("Route chronology", errs)

    # 6. recovery cargo
    errs = []
    for vid, r in plan.routes.items():
        picked = set()
        for s in r.stops:
            if s.kind == "pickup":
                f = plan.failures.get(s.recover_from)
                if not f:
                    errs.append(f"{vid}: pickup from non-failed vehicle {s.recover_from}")
                elif s.location != f["location"]:
                    errs.append(f"{vid}: pickup location differs from breakdown location")
                elif s.ready_at < f["time"] - EPS:
                    errs.append(f"{vid}: pickup scheduled before breakdown time")
                picked.add(s.recover_from)
            elif s.id in plan.recover and plan.recover[s.id] not in picked:
                errs.append(f"{s.id}: delivered before its cargo is collected from {plan.recover[s.id]}")
    chk("Cargo recovery from failed vehicles", errs)

    # 6b. reload stops must be at the depot
    errs = []
    for vid, r in plan.routes.items():
        for s in r.stops:
            if s.kind == "reload" and s.location != env.depot:
                errs.append(f"{vid}: reload stop {s.id} at {s.location}, must be at depot {env.depot}")
    chk("Reload stops at depot", errs)

    # 7. completed work preserved
    errs = []
    if prior is not None and prior_env is not None and now is not None:
        keys = ("stop_id", "kind", "location", "arrival", "start", "depart", "wait")
        for vid, r in prior.routes.items():
            expected = list(prior.history.get(vid, []))
            for tl in _timeline(r, prior_env, prior.recover):
                if tl["depart"] <= now + EPS:
                    expected.append({"stop_id": tl["stop"].id, "kind": tl["stop"].kind, "location": tl["stop"].location,
                                     "arrival": tl["arrival"], "start": tl["start"], "depart": tl["depart"],
                                     "wait": tl["start"] - tl["arrival"]})
            got = {(x["stop_id"]): x for x in plan.history.get(vid, [])}
            for e in expected:
                g = got.get(e["stop_id"])
                if g is None:
                    errs.append(f"{vid}: completed stop {e['stop_id']} missing from history")
                elif any(abs(float(g[k]) - float(e[k])) > 1e-3 if k in ("arrival", "start", "depart", "wait") else g[k] != e[k] for k in keys):
                    errs.append(f"{vid}: completed stop {e['stop_id']} was altered")
    chk("Completed deliveries preserved unchanged", errs)

    # 8. unassigned explained
    errs = [f"{d}: no reason recorded" for d, i in plan.unassigned.items() if not (i or {}).get("reason")]
    chk("Every unfulfilled order has an explicit reason", errs)

    errors = [e for c in checks for e in c["details"]]
    return {"valid": not errors, "checks": checks, "errors": errors}
