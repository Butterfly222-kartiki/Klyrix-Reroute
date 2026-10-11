"""Plan object: pending routes + immutable completed history + explicit unassigned list."""
from __future__ import annotations
import copy
from dataclasses import dataclass, field
from typing import Dict, List
from .schedule import Route, Env, RouteEval, evaluate_route


@dataclass
class Plan:
    routes: Dict[str, Route]
    history: Dict[str, List[dict]] = field(default_factory=dict)   # completed rows, frozen
    unassigned: Dict[str, dict] = field(default_factory=dict)      # did -> {reason, proven, category}
    failures: Dict[str, dict] = field(default_factory=dict)        # vid -> {time, location}
    recover: Dict[str, str] = field(default_factory=dict)          # did -> failed vehicle holding cargo
    now: float = 0.0
    label: str = "initial"
    reload_seq: int = 0                                            # counter for reload stop IDs

    def copy(self) -> "Plan":
        return copy.deepcopy(self)

    def evaluate(self, env: Env) -> Dict[str, RouteEval]:
        return {vid: evaluate_route(r, env, self.recover, full=True) for vid, r in self.routes.items()}

    def locate(self, env: Env) -> Dict[str, dict]:
        """did -> {state, vehicle, row, seq}. state in completed | pending | unassigned."""
        out: Dict[str, dict] = {}
        for vid, rows in self.history.items():
            for r in rows:
                if r["kind"] == "deliver":
                    out[r["stop_id"]] = {"state": "completed", "vehicle": vid, "row": r, "seq": None}
        for vid, ev in self.evaluate(env).items():
            seq = 0
            for r in ev.rows:
                if r["kind"] == "deliver":
                    out[r["stop_id"]] = {"state": "pending", "vehicle": vid, "row": r, "seq": seq}
                    seq += 1
        for did, info in self.unassigned.items():
            out[did] = {"state": "unassigned", "vehicle": None, "row": None, "seq": None, "info": info}
        return out

    def metrics(self, env: Env) -> dict:
        evs = self.evaluate(env)
        trav = sum(r["leg"] for rows in self.history.values() for r in rows)
        trav += sum(e.travel for e in evs.values())
        wait = sum(r["wait"] for rows in self.history.values() for r in rows) + sum(e.wait for e in evs.values())
        loc = self.locate(env)
        n = len(env.deliveries)
        done = sum(1 for v in loc.values() if v["state"] == "completed")
        pend = sum(1 for v in loc.values() if v["state"] == "pending")
        util = {}
        for vid, v in env.vehicles.items():
            peaks = [e.peak_load for e in [evs.get(vid)] if e]
            hist_peak = max([r["load_after"] for r in self.history.get(vid, [])] or [0])
            util[vid] = round(100 * max(peaks + [hist_peak]) / v.capacity, 1)
        return {"deliveries": n, "completed": done, "pending_assigned": pend,
                "unfulfilled": len(self.unassigned), "total_travel": round(trav, 1),
                "total_wait": round(wait, 1), "peak_utilization_pct": util}
