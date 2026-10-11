"""Current-state replanning: freeze completed work, apply the incident, repair, reinsert pending work only."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List

from .incidents import Incident, ROAD_CLOSURE, BREAKDOWN, URGENT
from .models import Closure, Delivery, EPS, fmt_time
from .plan import Plan
from .planner import insert_deliveries, order_key, order_key_alt
from .schedule import Env, Route, Stop, evaluate_route


@dataclass
class ReplanResult:
    plan: Plan
    env: Env
    notes: Dict[str, str] = field(default_factory=dict)   # did -> why it was touched
    log: List[str] = field(default_factory=list)
    strategy: str = "repair"


def snapshot(plan: Plan, env: Env, t: float) -> Plan:
    """State at time t: completed stops move to immutable history; the stop currently being
    driven to / served is *committed* (locked); everything after it is pending."""
    new = plan.copy()
    new.now = t
    for vid, route in plan.routes.items():
        if vid in plan.failures:
            continue
        ev = evaluate_route(route, env, plan.recover, full=True)
        done = 0
        for row in ev.rows:
            if row["depart"] <= t + EPS:
                done += 1
            else:
                break
        hist = new.history.setdefault(vid, [])
        for row in ev.rows[:done]:
            hist.append({**row, "vehicle": vid, "status": "completed"})
            if row["kind"] == "pickup":   # cargo is now physically on this vehicle
                rf = route.stops[ev.rows.index(row)].recover_from
                for x in route.stops[done:]:
                    if x.kind == "deliver" and new.recover.get(x.id) == rf:
                        new.recover.pop(x.id, None)
        origin = ev.rows[done - 1]["location"] if done else route.origin
        otime = ev.rows[done - 1]["depart"] if done else route.origin_time
        stops = [Stop(**{**s.to_dict(), "locked": False}) for s in route.stops[done:]]
        if stops and otime < t - EPS:
            stops[0].locked = True
        new.routes[vid] = Route(vid, origin, otime, stops)
    return new


def _stuck_location(route: Route, env: Env, recover: Dict[str, str], t: float) -> tuple:
    """Return (location, updated_env).  If the vehicle is mid-leg at time t, a virtual node
    STALL:<vid> is inserted into the environment with interpolated travel times."""
    ev = evaluate_route(route, env, recover, full=True)
    if not ev.rows:
        return route.origin, env
    # Find which leg the vehicle is on at time t
    prev_loc = route.origin
    prev_depart = route.origin_time
    for i, row in enumerate(ev.rows):
        if row["arrival"] > t + EPS:
            # Vehicle is mid-transit between prev_loc and row["location"]
            leg_duration = row["arrival"] - prev_depart
            if leg_duration < EPS:
                return prev_loc, env
            elapsed = t - prev_depart
            fraction = min(max(elapsed / leg_duration, 0.0), 1.0)
            if fraction < EPS:
                return prev_loc, env
            if fraction > 1.0 - EPS:
                return row["location"], env
            # Create a virtual stall location with interpolated distances
            stall_id = f"STALL:{route.vehicle_id}"
            return _add_stall_location(env, stall_id, prev_loc, row["location"], fraction), env
        if row["depart"] > t + EPS and row["arrival"] <= t + EPS:
            # Vehicle has arrived but hasn't departed — at this stop's location
            return row["location"], env
        prev_loc = row["location"]
        prev_depart = row["depart"]
    return prev_loc, env


def _add_stall_location(env: Env, stall_id: str, from_loc: str, to_loc: str, fraction: float) -> str:
    """Add a virtual stall node with interpolated travel times. Uses linear interpolation
    of base distances: dist(stall, X) ≈ (1-f)*dist(from, X) + f*dist(to, X)."""
    if stall_id in env.locations:
        return stall_id  # already created
    env.locations[stall_id] = {}
    env.matrix[stall_id] = {}
    for loc in list(env.matrix.keys()):
        if loc == stall_id:
            continue
        # Distance from stall to loc: interpolate
        d_from = env.matrix.get(from_loc, {}).get(loc, 0.0)
        d_to = env.matrix.get(to_loc, {}).get(loc, 0.0)
        d_interp = (1.0 - fraction) * d_from + fraction * d_to
        # Distance from loc to stall: interpolate (reverse)
        d_from_r = env.matrix.get(loc, {}).get(from_loc, 0.0)
        d_to_r = env.matrix.get(loc, {}).get(to_loc, 0.0)
        d_interp_r = (1.0 - fraction) * d_from_r + fraction * d_to_r
        env.matrix[stall_id][loc] = max(d_interp, 0.0)
        env.matrix.setdefault(loc, {})[stall_id] = max(d_interp_r, 0.0)
    env.matrix[stall_id][stall_id] = 0.0
    # Rebuild the travel model with the new location
    env.travel = env.travel.__class__(env.matrix, env.closures)
    return stall_id


def _cleanup_pickups(route: Route, recover: Dict[str, str]) -> None:
    need = {recover.get(s.id) for s in route.stops if s.kind == "deliver"}
    route.stops = [s for s in route.stops if s.kind not in ("pickup", "reload") or
                   (s.kind == "pickup" and (s.recover_from in need or s.locked)) or
                   (s.kind == "reload" and s.locked)]


def apply_incident(plan: Plan, env: Env, inc: Incident, strategy: str = "repair") -> ReplanResult:
    t = inc.time
    new = snapshot(plan, env, t)
    notes: Dict[str, str] = {}
    log = [f"Frozen state at {fmt_time(t)}: " + ", ".join(
        f"{v}: {len(new.history.get(v, []))} done" for v in sorted(new.routes))]
    pool: List[str] = []
    env2 = env
    if inc.type == ROAD_CLOSURE:
        d = inc.data
        c = Closure(d["a"], d["b"], d["start"], d["end"], d["extra"], d["factor"], f"C{len(env.closures) + 1}")
        env2 = env.evolve(closures=list(env.closures) + [c])
        log.append(f"Travel time {c.a}-{c.b} increased during {fmt_time(c.start)}-{fmt_time(c.end)}.")
    elif inc.type == URGENT:
        dl = Delivery(**inc.data["delivery"])
        env2 = env.evolve(add_deliveries=[dl])
        pool.append(dl.id)
        notes[dl.id] = f"Urgent order received {fmt_time(t)}"
        log.append(f"Urgent order {dl.id} added to the pending pool.")
    elif inc.type == BREAKDOWN:
        vid = inc.data["vehicle_id"]
        route = new.routes[vid]
        loc, env = _stuck_location(route, env, new.recover, t)
        new.failures[vid] = {"time": t, "location": loc}
        for s in route.stops:
            if s.kind == "deliver":
                rf = new.recover.get(s.id) or vid   # cargo may still sit at an earlier breakdown
                new.recover[s.id] = rf
                pool.append(s.id)
                notes[s.id] = (f"{vid} broke down at {fmt_time(t)} at {loc}; cargo must be collected"
                               if rf == vid else f"Carrier {vid} failed before collecting cargo left by {rf}")
        new.routes[vid] = Route(vid, loc, t, [])
        log.append(f"{vid} marked failed at {fmt_time(t)} (location {loc}); {len(pool)} pending orders to recover.")
        env2 = env   # env may now include the STALL node

    prefer: Dict[str, str] = {}
    if strategy == "rebuild":
        for vid, r in new.routes.items():
            if vid in new.failures:
                continue
            lc = r.locked_count()
            for s in r.stops[lc:]:
                if s.kind == "deliver":
                    pool.append(s.id)
                    prefer[s.id] = vid
            r.stops = r.stops[:lc]
            _cleanup_pickups(r, new.recover)
        log.append("Fallback strategy: all uncommitted pending deliveries re-inserted from scratch.")
    else:
        for vid, r in new.routes.items():
            if vid in new.failures:
                continue
            while True:
                ev = evaluate_route(r, env2, new.recover, full=True)
                bad = [v for v in ev.violations if v["type"] in ("window", "shift_end")]
                if ev.feasible or not bad:
                    break
                # Find the stop whose removal best fixes violations
                first_bad = bad[0]["index"]
                if r.stops[first_bad].locked:
                    break
                # Try evicting the violated stop itself, or the stop just before it
                # (the causal stop that pushed things late)
                best_evict, best_evict_fixes = first_bad, 0
                lc = r.locked_count()
                for candidate_idx in range(lc, min(first_bad + 1, len(r.stops))):
                    s_cand = r.stops[candidate_idx]
                    if s_cand.locked or s_cand.kind != "deliver":
                        continue
                    trial = r.stops[:candidate_idx] + r.stops[candidate_idx + 1:]
                    trial_ev = evaluate_route(Route(vid, r.origin, r.origin_time, trial), env2, new.recover, full=True)
                    fixes = len(ev.violations) - len(trial_ev.violations)
                    if fixes > best_evict_fixes:
                        best_evict, best_evict_fixes = candidate_idx, fixes
                i = best_evict
                s = r.stops.pop(i)
                row = ev.rows[i]
                pool.append(s.id)
                prefer[s.id] = vid
                notes[s.id] = (f"On {vid} it would be served {fmt_time(row['start'])}, after its deadline "
                               f"{fmt_time(row['tw_end'])}, following the disruption"
                               if row.get("tw_end") else
                               f"Evicted from {vid} to resolve route violation")
                _cleanup_pickups(r, new.recover)
            if evaluate_route(r, env2, new.recover, full=True).violations:
                log.append(f"Warning: route {vid} still has violations after repair.")
        if pool:
            log.append(f"{len(pool)} deliveries removed from routes for reinsertion.")
    retry = [d for d in new.unassigned if d not in pool]
    pool = list(dict.fromkeys(pool + retry))
    for d in pool:
        new.unassigned.pop(d, None)
    insert_deliveries(new, env2, pool, prefer, key=order_key_alt if strategy == "rebuild" else order_key)

    # --- Post-pass: relocate + 2-opt improvement (accepted only if validator passes) ---
    from .planner import post_pass
    improved = post_pass(new, env2)
    if improved:
        log.append(f"Post-pass: {improved} relocate/2-opt improvement(s) applied.")

    for d in pool:
        if d in new.unassigned:
            notes[d] = new.unassigned[d]["reason"]
    new.label = f"after: {inc.describe()}"
    return ReplanResult(new, env2, notes, log, strategy)


