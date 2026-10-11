"""Original-vs-revised comparison: every delivery classified kept / moved / broken (+ new)."""
from __future__ import annotations
from typing import Dict, List
from .models import fmt_time
from .plan import Plan
from .schedule import Env


def _order(loc: Dict[str, dict], vid: str) -> List[str]:
    return [d for d, v in sorted(((d, v) for d, v in loc.items() if v["vehicle"] == vid and v["state"] == "pending"),
                                 key=lambda kv: kv[1]["seq"])]


def compare_plans(before: Plan, env_before: Env, after: Plan, env_after: Env, notes: Dict[str, str] = None) -> List[dict]:
    notes = notes or {}
    lb, la = before.locate(env_before), after.locate(env_after)
    rank_b, rank_a = {}, {}
    for vid in env_after.vehicles:
        ob, oa = _order(lb, vid), _order(la, vid)
        common_b = [x for x in ob if x in oa]
        common_a = [x for x in oa if x in ob]
        for i, x in enumerate(common_b):
            rank_b[x] = i
        for i, x in enumerate(common_a):
            rank_a[x] = i
    rows = []
    for did, d in sorted(env_after.deliveries.items()):
        b, a = lb.get(did), la.get(did)
        eta_b = b["row"]["start"] if b and b["row"] else None
        eta_a = a["row"]["start"] if a and a["row"] else None
        base = {"delivery": did, "location": d.location, "weight": d.weight,
                "window": f"{fmt_time(d.tw_start)}-{fmt_time(d.tw_end)}",
                "vehicle_before": b["vehicle"] if b else None, "vehicle_after": a["vehicle"] if a else None,
                "eta_before": eta_b, "eta_after": eta_a,
                "arrival_after": a["row"]["arrival"] if a and a["row"] else None,
                "wait_after": a["row"]["wait"] if a and a["row"] else None}
        if a["state"] == "unassigned":
            info = a["info"]
            was = b is not None and b["state"] != "unassigned"
            status, tag = "broken", ("newly_unfulfilled" if was else "unfulfilled_before_and_after")
            reason = info["reason"]
            if was and did in notes and notes[did] != info["reason"]:
                reason = notes[did] + ". Then: " + info["reason"]
        elif a["state"] == "completed":
            status, tag, reason = "kept", "completed", "Already delivered before the disruption; record preserved."
        elif b is None:
            status, tag, reason = "new", "new_urgent", notes.get(did, "New order") + f"; inserted on {a['vehicle']}"
        elif b["state"] == "unassigned":
            status, tag, reason = "moved", "recovered", f"Previously unplaced; now assigned to {a['vehicle']}"
        elif b["vehicle"] != a["vehicle"]:
            status, tag = "moved", "reassigned"
            reason = notes.get(did, "Reassigned") + f" -> now on {a['vehicle']} (was {b['vehicle']})"
        elif b["state"] == "pending" and rank_b.get(did) != rank_a.get(did):
            # Sequence changed but vehicle stayed the same
            status, tag, reason = "kept", "resequenced", f"Visit order on {a['vehicle']} changed"
        else:
            status = "kept"
            changed = eta_b is not None and eta_a is not None and abs(eta_a - eta_b) > 0.5
            tag = "eta_changed" if changed else "unchanged"
            reason = (f"Same vehicle; ETA {fmt_time(eta_b)} -> {fmt_time(eta_a)}" if changed else "Unaffected")
        base.update(status=status, tag=tag, reason=reason,
                    eta_delta=(eta_a - eta_b) if eta_a is not None and eta_b is not None else None)
        rows.append(base)
    return rows


def summarize(rows: List[dict]) -> dict:
    out = {"kept": 0, "moved": 0, "broken": 0, "new": 0, "stops_moved": 0}
    for r in rows:
        out[r["status"]] += 1
        # Only count as "stops_moved" if vehicle changed or delivery was recovered from unassigned
        if r["tag"] in ("reassigned", "recovered"):
            out["stops_moved"] += 1
    out["total"] = len(rows)
    return out
