"""Tests for vehicle shift_end / return-to-depot deadline enforcement."""
from helpers import demo_dict
from reroute.models import Scenario, ValidationError
from reroute.engine import Session
from reroute.validator import validate_plan
from reroute.schedule import Env, Route, Stop, evaluate_route
from reroute.plan import Plan


def test_shift_end_enforced_in_evaluate_route():
    """A route whose depot return exceeds shift_end should be infeasible."""
    d = demo_dict()
    d["vehicles"] = [{"id": "V1", "capacity": 70, "start_time": "08:00", "shift_end": "09:00"}]
    d["deliveries"] = [
        {"id": "D1", "location": "C7", "weight": 10, "tw_start": "08:00", "tw_end": "14:00"},
    ]
    s = Scenario.from_dict(d)
    env = Env.from_scenario(s)
    # C7 is ~24.5 min from DEPOT; round trip = ~49 min + 5 service = ~54 min
    # Departure 08:00, return ~08:55 — should fit in 09:00 shift end
    route_ok = Route("V1", "DEPOT", 480, [Stop("D1", "deliver", "C7")])
    ev = evaluate_route(route_ok, env, {})
    assert ev.feasible, f"Should fit within shift: end {ev.end_time}"

    # Now with tight shift_end at 08:45 — won't fit
    d["vehicles"][0]["shift_end"] = "08:45"
    s2 = Scenario.from_dict(d)
    env2 = Env.from_scenario(s2)
    route_tight = Route("V1", "DEPOT", 480, [Stop("D1", "deliver", "C7")])
    ev2 = evaluate_route(route_tight, env2, {})
    assert not ev2.feasible
    assert any(v["type"] == "shift_end" for v in ev2.violations)


def test_shift_end_enforced_in_validator():
    """Validator independently checks shift_end."""
    d = demo_dict()
    d["vehicles"] = [{"id": "V1", "capacity": 70, "start_time": "08:00", "shift_end": "08:45"}]
    d["deliveries"] = [
        {"id": "D1", "location": "C7", "weight": 10, "tw_start": "08:00", "tw_end": "14:00"},
    ]
    s = Scenario.from_dict(d)
    env = Env.from_scenario(s)
    plan = Plan(routes={"V1": Route("V1", "DEPOT", 480, [Stop("D1", "deliver", "C7")])}, now=480)
    rep = validate_plan(plan, env)
    assert not rep["valid"]
    assert any("shift end" in e.lower() for e in rep["errors"])


def test_shift_end_planner_respects_deadline():
    """Planner should not assign stops that would cause shift_end violations."""
    d = demo_dict()
    # Give vehicles very tight shift ends — some deliveries should be unassigned
    for v in d["vehicles"]:
        v["shift_end"] = "09:30"   # only 90 minutes from 08:00
    s = Session(Scenario.from_dict(d))
    s.plan_initial()
    assert s.validation["valid"]
    # With tight shifts, not all 14 deliveries can be completed
    assert len(s.plan.unassigned) > 0


def test_shift_end_default_no_constraint():
    """Without shift_end, vehicles default to 24:00 — no constraint."""
    s = Session(Scenario.from_dict(demo_dict()))
    s.plan_initial()
    assert s.validation["valid"]
    # All deliveries should fit without shift_end constraint
    assert not s.plan.unassigned


def test_shift_end_validation_rejects_invalid():
    """shift_end before start_time should raise ValidationError."""
    d = demo_dict()
    d["vehicles"][0]["shift_end"] = "07:00"  # before start_time 08:00
    try:
        Scenario.from_dict(d)
        assert False, "Should have raised ValidationError"
    except ValidationError as e:
        assert "shift_end" in str(e).lower()
