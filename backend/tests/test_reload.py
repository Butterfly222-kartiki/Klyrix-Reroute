"""Tests for depot reload stops and proper urgent parcel handling."""
from helpers import session, demo_dict
from reroute.models import Scenario
from reroute.engine import Session
from reroute.validator import validate_plan
from reroute.schedule import Env, Route, Stop, evaluate_route


def test_urgent_order_inserts_reload_when_vehicle_departed():
    """After a vehicle has departed (via breakdown freezing time), an urgent order
    should cause a reload stop if the order is placed on a departed vehicle."""
    s = session()
    # Apply a breakdown to freeze time
    r = s.preview({"type": "vehicle_breakdown", "vehicle_id": "V1", "time": "09:10"})
    assert r["accepted"] and r["validation"]["valid"]
    s.apply(r["id"])
    # Now add an urgent order — vehicles V2/V3 have departed
    r2 = s.preview({"type": "urgent_order", "time": "09:15",
                    "delivery": {"location": "C11", "weight": 3, "tw_start": "09:15", "tw_end": "12:00"}})
    assert r2["ok"]
    if r2["accepted"]:
        # The urgent order should be placed; check validation passes
        assert r2["validation"]["valid"]
        s.apply(r2["id"])
        assert s.validation["valid"]
        # Check: if vehicle has history (departed), a reload stop should exist
        for vid, route in s.plan.routes.items():
            has_urgent = any(st.id == "U1" for st in route.stops)
            if has_urgent and s.plan.history.get(vid):
                has_reload = any(st.kind == "reload" for st in route.stops)
                # Vehicle departed -> reload should be present
                assert has_reload, f"Departed vehicle {vid} has urgent delivery but no reload stop"


def test_urgent_order_no_reload_when_vehicle_at_depot():
    """When the initial plan has not been advanced, vehicles haven't departed yet.
    An urgent order should not require a reload stop."""
    s = session()
    # Add urgent order at the beginning — vehicles haven't departed yet
    r = s.preview({"type": "urgent_order", "time": "08:00",
                   "delivery": {"location": "C11", "weight": 3, "tw_start": "08:00", "tw_end": "12:00"}})
    assert r["ok"] and r["accepted"]
    assert r["validation"]["valid"]
    # Since no vehicle has departed, no reload should be needed
    s.apply(r["id"])
    for vid, route in s.plan.routes.items():
        has_urgent = any(st.id == "U1" for st in route.stops)
        if has_urgent:
            has_reload = any(st.kind == "reload" for st in route.stops)
            assert not has_reload, f"Vehicle {vid} at depot has unnecessary reload stop"


def test_reload_stop_resets_capacity():
    """A reload stop should reset capacity. A route that would exceed capacity without
    reload should be feasible with one."""
    d = demo_dict()
    d["vehicles"] = [{"id": "V1", "capacity": 25, "start_time": "08:00"}]
    d["deliveries"] = [
        {"id": "D1", "location": "C1", "weight": 15, "tw_start": "08:00", "tw_end": "12:00"},
        {"id": "D2", "location": "C2", "weight": 15, "tw_start": "08:00", "tw_end": "14:00"},
    ]
    s = Scenario.from_dict(d)
    env = Env.from_scenario(s)
    
    # Without reload: both deliveries = 30 weight > 25 capacity — infeasible
    route_no_reload = Route("V1", "DEPOT", 480, [
        Stop("D1", "deliver", "C1"),
        Stop("D2", "deliver", "C2"),
    ])
    ev = evaluate_route(route_no_reload, env, {})
    assert not ev.feasible, "Route without reload should be infeasible due to capacity"
    
    # With reload: deliver D1, return to depot (reload), deliver D2
    route_with_reload = Route("V1", "DEPOT", 480, [
        Stop("D1", "deliver", "C1"),
        Stop("RELOAD:test", "reload", "DEPOT"),
        Stop("D2", "deliver", "C2"),
    ])
    ev2 = evaluate_route(route_with_reload, env, {})
    assert ev2.feasible, f"Route with reload should be feasible: {ev2.violations}"
    
    # Verify capacity at each point
    assert ev2.rows[0]["load_after"] == 0.0  # after delivering D1, was carrying 15, now 0
    assert ev2.rows[1]["load_after"] == 15.0  # after reload, loaded D2's weight
    assert ev2.rows[2]["load_after"] == 0.0  # after delivering D2


def test_reload_capacity_validated():
    """Validator should independently verify capacity through reload stops."""
    d = demo_dict()
    d["vehicles"] = [{"id": "V1", "capacity": 25, "start_time": "08:00"}]
    d["deliveries"] = [
        {"id": "D1", "location": "C1", "weight": 15, "tw_start": "08:00", "tw_end": "12:00"},
        {"id": "D2", "location": "C2", "weight": 15, "tw_start": "08:00", "tw_end": "14:00"},
    ]
    s = Scenario.from_dict(d)
    env = Env.from_scenario(s)
    from reroute.plan import Plan
    
    # Valid plan with reload
    plan = Plan(routes={"V1": Route("V1", "DEPOT", 480, [
        Stop("D1", "deliver", "C1"),
        Stop("RELOAD:v1", "reload", "DEPOT"),
        Stop("D2", "deliver", "C2"),
    ])}, now=480)
    rep = validate_plan(plan, env)
    assert rep["valid"], f"Valid reload plan rejected: {rep['errors']}"


def test_reload_must_be_at_depot():
    """A reload stop at a non-depot location should fail validation."""
    d = demo_dict()
    d["vehicles"] = [{"id": "V1", "capacity": 50, "start_time": "08:00"}]
    d["deliveries"] = [
        {"id": "D1", "location": "C1", "weight": 10, "tw_start": "08:00", "tw_end": "14:00"},
    ]
    s = Scenario.from_dict(d)
    env = Env.from_scenario(s)
    from reroute.plan import Plan
    
    plan = Plan(routes={"V1": Route("V1", "DEPOT", 480, [
        Stop("RELOAD:bad", "reload", "C5"),  # NOT at depot
        Stop("D1", "deliver", "C1"),
    ])}, now=480)
    rep = validate_plan(plan, env)
    assert not rep["valid"], "Reload at non-depot should be invalid"
    assert any("depot" in e.lower() for e in rep["errors"])


def test_urgent_rejected_if_window_too_tight_even_with_reload():
    """If the time window is so tight that even with reload the vehicle can't make it,
    the order should be reported as broken/unfulfilled."""
    s = session()
    r = s.preview({"type": "vehicle_breakdown", "vehicle_id": "V1", "time": "09:10"})
    s.apply(r["id"])
    # Urgent order with impossibly tight window — 5 min window at a far location
    r2 = s.preview({"type": "urgent_order", "time": "09:15",
                    "delivery": {"location": "C7", "weight": 3, "tw_start": "09:15", "tw_end": "09:20"}})
    assert r2["ok"]
    # Should be broken (unfulfilled) because window is too tight
    row = [x for x in r2["comparison"] if x["delivery"] == "U1"][0]
    assert row["status"] == "broken"
    assert row["reason"]
