"""Session / state manager: holds the active plan, previews incidents, validates, applies, falls back."""
from __future__ import annotations
import time
from typing import Callable, Dict, List, Optional

from .compare import compare_plans, summarize
from .incidents import Incident, IncidentError, parse_text, validate_incident
from .models import Scenario, fmt_time
from .plan import Plan
from .planner import build_initial_plan, order_key, order_key_alt
from .replan import ReplanResult, apply_incident
from .schedule import Env
from .validator import validate_plan


class PlanRejected(RuntimeError):
    pass


def plan_view(plan: Plan, env: Env) -> dict:
    evs = plan.evaluate(env)
    vehicles = {}
    for vid, v in env.vehicles.items():
        r, ev = plan.routes[vid], evs[vid]
        vehicles[vid] = {"capacity": v.capacity, "start_time": v.start_time, "failed": plan.failures.get(vid),
                         "origin": r.origin, "origin_time": r.origin_time,
                         "history": plan.history.get(vid, []), "rows": ev.rows,
                         "travel": round(ev.travel, 1), "end_time": round(ev.end_time, 1),
                         "peak_load": ev.peak_load, "load_now": ev.initial_load}
    return {"now": plan.now, "label": plan.label, "vehicles": vehicles, "unassigned": plan.unassigned,
            "metrics": plan.metrics(env), "recover": plan.recover}


class Session:
    def __init__(self, scenario: Scenario, planner_override: Optional[Callable] = None):
        self.scenario = scenario
        self.env0 = Env.from_scenario(scenario)
        self.env = self.env0
        self.plan: Optional[Plan] = None
        self.initial_plan: Optional[Plan] = None
        self.validation: Optional[dict] = None
        self.events: List[dict] = []
        self.pending: Dict[str, dict] = {}
        self.planner_override = planner_override
        self._seq = 0
        self.last_comparison: Optional[dict] = None
        self.history_stack: List[tuple] = []  # For undo: (plan, env, validation, events_copy, last_comparison_copy)

    # ---------------------------------------------------------------- initial plan
    def plan_initial(self) -> dict:
        t0 = time.perf_counter()
        for key in (order_key, order_key_alt):          # fallback ordering if first plan fails validation
            plan = build_initial_plan(self.env0, key=key)
            rep = validate_plan(plan, self.env0)
            if rep["valid"]:
                break
        else:
            raise PlanRejected("Initial plan failed validation: " + "; ".join(rep["errors"]))
        self.plan = self.initial_plan = plan
        self.env = self.env0
        self.validation = rep
        self.events, self.pending, self.last_comparison = [], {}, None
        return {"validation": rep, "ms": round((time.perf_counter() - t0) * 1000, 1)}

    # ---------------------------------------------------------------- incidents
    def _all_ids(self):
        return list(self.env.deliveries)

    def _compute(self, inc: Incident):
        attempts = []
        for strat in ("repair", "rebuild"):
            fn = self.planner_override or apply_incident
            t0 = time.perf_counter()
            res: ReplanResult = fn(self.plan, self.env, inc, strat)
            rep = validate_plan(res.plan, res.env, prior=self.plan, prior_env=self.env, now=inc.time)
            attempts.append({"strategy": strat, "valid": rep["valid"], "errors": rep["errors"][:6],
                             "ms": round((time.perf_counter() - t0) * 1000, 1)})
            if rep["valid"]:
                return res, rep, attempts
        return None, rep, attempts

    def preview(self, raw: Optional[dict] = None, text: Optional[str] = None) -> dict:
        if self.plan is None:
            raise PlanRejected("Create the initial plan first")
        proposal = None
        if text is not None:
            proposal = parse_text(text, self.env, self.plan.now, self.plan.failures, self._all_ids())
            if not proposal["ok"]:
                return {"ok": False, "errors": proposal["errors"], "proposal": proposal,
                        "message": "Report rejected - nothing was changed."}
            
            # Check if this is a multi-incident response
            if "incidents" in proposal:
                # Multiple incidents: create separate proposals
                proposals_out = []
                for i, inc_data in enumerate(proposal["incidents"]):
                    inc = validate_incident({**inc_data["data"], "type": inc_data["type"],
                                           "time": inc_data["time"], **(
                        {"delivery": inc_data["data"]["delivery"]} if inc_data["type"] == "urgent_order" else {})},
                                          self.env, self.plan.now, self.plan.failures, self._all_ids())
                    inc.source, inc.raw_text = "text", text
                    inc.interpretation = proposal["interpretations"][i]
                    inc.assumptions = proposal.get("assumptions", [])
                    
                    res, rep, attempts = self._compute(inc)
                    self._seq += 1
                    pid = f"P{self._seq}"
                    item = {"id": pid, "incident": inc, "result": res, "validation": rep, "attempts": attempts,
                            "requires_confirmation": inc.source == "text"}
                    out_single = {"ok": True, "id": pid, "incident": inc.to_dict(), 
                                "requires_confirmation": item["requires_confirmation"],
                                "validation": rep, "attempts": attempts, "applied": False}
                    if res is None:
                        out_single.update(accepted=False, message="No valid revised plan could be produced. "
                                       "The last valid plan stays active.")
                    else:
                        rows = compare_plans(self.plan, self.env, res.plan, res.env, res.notes)
                        item["rows"] = rows
                        out_single.update(accepted=True, comparison=rows, summary=summarize(rows), log=res.log,
                                       strategy=res.strategy, revised=plan_view(res.plan, res.env))
                    self.pending[pid] = item
                    proposals_out.append(out_single)
                
                return {"ok": True, "multiple": True, "proposals": proposals_out, 
                       "message": f"{len(proposals_out)} incidents detected. Review and apply each separately."}
            
            # Single incident from text
            inc = validate_incident({**proposal["incident"]["data"], "type": proposal["incident"]["type"],
                                     "time": proposal["incident"]["time"], **(
                {"delivery": proposal["incident"]["data"]["delivery"]} if proposal["incident"]["type"] == "urgent_order" else {})},
                                    self.env, self.plan.now, self.plan.failures, self._all_ids())
            inc.source, inc.raw_text = "text", text
            inc.interpretation, inc.assumptions = proposal["interpretation"], proposal["assumptions"]
        else:
            try:
                inc = validate_incident(raw, self.env, self.plan.now, self.plan.failures, self._all_ids())
            except IncidentError as e:
                return {"ok": False, "errors": e.errors, "message": "Incident rejected - nothing was changed."}
        res, rep, attempts = self._compute(inc)
        self._seq += 1
        pid = f"P{self._seq}"
        item = {"id": pid, "incident": inc, "result": res, "validation": rep, "attempts": attempts,
                "requires_confirmation": inc.source == "text"}
        out = {"ok": True, "id": pid, "incident": inc.to_dict(), "requires_confirmation": item["requires_confirmation"],
               "validation": rep, "attempts": attempts, "applied": False}
        if res is None:
            out.update(accepted=False, message="No valid revised plan could be produced. "
                       "The last valid plan stays active.")
        else:
            rows = compare_plans(self.plan, self.env, res.plan, res.env, res.notes)
            item["rows"] = rows
            out.update(accepted=True, comparison=rows, summary=summarize(rows), log=res.log,
                       strategy=res.strategy, revised=plan_view(res.plan, res.env))
        self.pending[pid] = item
        return out

    def apply(self, pid: str, confirm: bool = False) -> dict:
        item = self.pending.get(pid)
        if item is None:
            raise PlanRejected(f"No pending incident {pid}")
        if item["requires_confirmation"] and not confirm:
            raise PlanRejected("Text-interpreted incidents need explicit dispatcher confirmation")
        res = item["result"]
        if res is None:
            raise PlanRejected("Candidate plan was invalid; it cannot be applied")
        
        # Save current state to history for undo
        import copy
        self.history_stack.append((
            copy.deepcopy(self.plan),
            copy.deepcopy(self.env),
            copy.deepcopy(self.validation),
            copy.deepcopy(self.events),
            copy.deepcopy(self.last_comparison)
        ))
        
        before, env_before = self.plan, self.env
        self.plan, self.env, self.validation = res.plan, res.env, item["validation"]
        self.last_comparison = {"rows": item["rows"], "summary": summarize(item["rows"]), "log": res.log,
                                "incident": item["incident"].to_dict(), "strategy": res.strategy}
        self.events.append({"time": item["incident"].time, "incident": item["incident"].to_dict(),
                            "summary": summarize(item["rows"]), "strategy": res.strategy})
        self.pending.clear()
        return {"ok": True, "applied": True}

    def cancel(self, pid: str) -> dict:
        self.pending.pop(pid, None)
        return {"ok": True}

    # ---------------------------------------------------------------- undo
    def undo(self) -> dict:
        """Undo the last applied incident by restoring from history stack."""
        if not self.history_stack:
            raise PlanRejected("Nothing to undo")
        plan, env, validation, events_copy, last_comparison_copy = self.history_stack.pop()
        self.plan = plan
        self.env = env
        self.validation = validation
        self.events = events_copy
        self.last_comparison = last_comparison_copy
        return {"ok": True, "message": "Last incident undone"}

    # ---------------------------------------------------------------- advance time
    def advance_time(self, minutes: float) -> dict:
        """Advance simulation time and commit completed stops to history."""
        if self.plan is None:
            raise PlanRejected("No active plan")
        import copy
        from .replan import snapshot
        
        new_time = self.plan.now + minutes
        # Use snapshot logic to commit completed stops
        snap = snapshot(self.plan, self.env, new_time)
        self.plan = snap
        return {"ok": True, "now": new_time, "message": f"Time advanced to {fmt_time(new_time)}"}

    # ---------------------------------------------------------------- report
    def report(self) -> str:
        """Generate a Markdown decision report from the event log."""
        if not self.events:
            return "# ReRoute Decision Report\n\nNo incidents have been applied yet.\n"
        
        lines = ["# ReRoute Decision Report\n"]
        lines.append(f"**Scenario**: {self.scenario.name}\n")
        lines.append(f"**Vehicles**: {len(self.scenario.vehicles)}\n")
        lines.append(f"**Deliveries**: {len(self.scenario.deliveries)}\n")
        lines.append(f"**Total Events**: {len(self.events)}\n\n")
        
        for i, evt in enumerate(self.events, 1):
            inc = evt["incident"]
            summary = evt.get("summary", {})
            strategy = evt.get("strategy", "repair")
            
            lines.append(f"## Event {i}\n")
            lines.append(f"**Incident**: {inc.get('description', 'N/A')}\n")
            lines.append(f"**Time**: {fmt_time(evt.get('time', 0))}\n")
            lines.append(f"**Type**: {inc.get('type', 'N/A')}\n")
            lines.append(f"**Strategy**: {strategy}\n")
            lines.append(f"**Summary**: kept {summary.get('kept', 0)}, moved {summary.get('moved', 0)}, broken {summary.get('broken', 0)}")
            if summary.get('new', 0) > 0:
                lines.append(f", new {summary['new']}")
            lines.append("\n\n")
        
        return "\n".join(lines)

    # ---------------------------------------------------------------- view
    def state(self) -> dict:
        s = self.scenario
        out = {"scenario": {"name": s.name, "depot": s.depot, "locations": s.locations,
                            "vehicles": [{"id": v.id, "capacity": v.capacity, "start_time": v.start_time, "shift_end": v.shift_end} for v in s.vehicles],
                            "deliveries": [d.__dict__ for d in self.env.deliveries.values()],
                            "closures": [c.__dict__ for c in self.env.closures]},
               "has_plan": self.plan is not None, "events": self.events,
               "pending": [{"id": k, "incident": v["incident"].to_dict()} for k, v in self.pending.items()]}
        if self.plan is not None:
            out.update(plan=plan_view(self.plan, self.env), validation=self.validation,
                       initial=plan_view(self.initial_plan, self.env0), last_comparison=self.last_comparison,
                       vs_original=compare_plans(self.initial_plan, self.env0, self.plan, self.env))
        return out
