import copy
from helpers import session, demo_dict
from reroute.models import Scenario, ValidationError, to_minutes
from reroute.engine import Session
from reroute.validator import validate_plan
from reroute.planner import build_initial_plan
from reroute.schedule import Env, Route, Stop, evaluate_route
from reroute.incidents import parse_text, validate_incident, IncidentError
from reroute.replan import apply_incident


def test_normal_day_valid_and_complete():
    s = session()
    assert s.validation["valid"]
    assert not s.plan.unassigned
    assigned = [st.id for r in s.plan.routes.values() for st in r.stops]
    assert sorted(assigned) == sorted(s.env.deliveries)


def test_waiting_time_when_early():
    s = session()
    row = s.state()["plan"]["vehicles"]["V2"]["rows"][0]   # D10 window opens 09:00, arrives ~08:24
    assert row["wait"] > 0 and abs(row["start"] - 540) < 1e-6


def test_capacity_rejected():
    d = demo_dict()
    d["vehicles"] = [{"id": "V1", "capacity": 20, "start_time": "08:00"}]
    d["deliveries"] = [{"id": "A", "location": "C1", "weight": 15, "tw_start": "08:00", "tw_end": "20:00"},
                       {"id": "B", "location": "C2", "weight": 15, "tw_start": "08:00", "tw_end": "20:00"}]
    s = Session(Scenario.from_dict(d)); s.plan_initial()
    assert len(s.plan.unassigned) == 1                       # second parcel cannot fit on the only vehicle
    env = s.env0
    bad = Route("V1", "DEPOT", 480, [Stop("A", "deliver", "C1"), Stop("B", "deliver", "C2")])
    assert not evaluate_route(bad, env, {}).feasible


def test_window_infeasible_is_proven_and_explained():
    d = demo_dict()
    d["deliveries"][0].update(tw_start="08:00", tw_end="08:05")     # C1 is ~20 min away
    s = Session(Scenario.from_dict(d)); s.plan_initial()
    info = s.plan.unassigned["D1"]
    assert info["proven"] and "Provably" in info["reason"]


def test_heuristic_failure_not_claimed_as_proof():
    s = session()
    r = s.preview({"type": "vehicle_breakdown", "vehicle_id": "V1", "time": "09:10"})
    broken = [x for x in r["comparison"] if x["status"] == "broken"]
    assert broken and all(x["reason"] for x in broken)
    assert any("Not proven impossible" in x["reason"] for x in broken)


def test_breakdown_preserves_completed_and_no_future_stops_on_failed():
    s = session()
    r = s.preview({"type": "vehicle_breakdown", "vehicle_id": "V1", "time": "09:10"})
    assert r["accepted"] and r["validation"]["valid"]
    s.apply(r["id"])
    # V1 should have some completed history before breakdown at 09:10
    assert len(s.plan.history["V1"]) > 0
    # All completed deliveries should be in history
    assert all(x["kind"] == "deliver" for x in s.plan.history["V1"])
    # V1 should have no pending stops (failed vehicle)
    assert s.plan.routes["V1"].stops == []
    assert "V1" in s.plan.failures
    # recovered cargo is explicitly picked up by another vehicle before delivery
    # (any delivery that was pending on V1 needs to be picked up first)
    for vid in s.plan.routes:
        if vid == "V1":
            continue
        v_stops = [x.id for x in s.plan.routes[vid].stops]
        for pickup_id in [x.id for x in s.plan.routes[vid].stops if x.kind == "pickup" and x.recover_from == "V1"]:
            # Check that all deliveries recovered from V1 come after the pickup
            for delivery in [x for x in s.plan.routes[vid].stops if x.kind == "deliver" and s.plan.recover.get(x.id) == "V1"]:
                assert v_stops.index(pickup_id) < v_stops.index(delivery.id)


def test_every_delivery_accounted_after_incident():
    s = session()
    r = s.preview({"type": "vehicle_breakdown", "vehicle_id": "V2", "time": "08:50"})
    assert len(r["comparison"]) == len(s.env.deliveries)
    assert sum(r["summary"][k] for k in ("kept", "moved", "broken", "new")) == r["summary"]["total"]


def test_road_closure_only_during_period():
    s = session()
    from reroute.models import Closure
    tm = s.env.travel.with_closures([Closure("DEPOT", "C12", 600, 660, 30)])
    base = tm.base("DEPOT", "C12")
    assert abs(tm.time("DEPOT", "C12", 500) - base) < 1e-6                   # before closure
    assert abs(tm.time("DEPOT", "C12", 700) - base) < 1e-6                   # after closure
    assert tm.time("DEPOT", "C12", 610) > base - 1e-9             # during: delay or detour, never faster


def test_closure_updates_etas_and_validates():
    s = session()
    r = s.preview({"type": "road_closure", "a": "DEPOT", "b": "C10", "start": "08:00", "end": "09:00", "extra": 45, "time": "08:00"})
    assert r["accepted"] and r["validation"]["valid"]


def test_urgent_order_inserted_or_reported():
    s = session()
    r = s.preview({"type": "urgent_order", "time": "08:45",
                   "delivery": {"location": "C11", "weight": 3, "tw_start": "08:45", "tw_end": "12:00"}})
    row = [x for x in r["comparison"] if x["delivery"] == "U1"][0]
    assert row["status"] in ("new", "broken") and row["reason"]
    assert row["status"] == "new"
    huge = s.preview({"type": "urgent_order", "time": "08:45",
                      "delivery": {"location": "C11", "weight": 500, "tw_start": "08:45", "tw_end": "12:00"}})
    row = [x for x in huge["comparison"] if x["delivery"] == "U1"][0]
    assert row["status"] == "broken" and "capacity" in row["reason"].lower()


def test_unknown_location_rejected_not_guessed():
    s = session()
    r = s.preview(text="The road between C1 and C99 is closed from 10:00 to 10:30")
    assert not r["ok"] and any("Unknown" in e for e in r["errors"])
    r = s.preview({"type": "road_closure", "a": "C1", "b": "NOWHERE", "start": "10:00", "end": "10:30", "extra": 10})
    assert not r["ok"]
    assert not s.pending


def test_text_incident_needs_confirmation_and_original_plan_stays_active():
    s = session()
    before = copy.deepcopy(s.plan.routes["V1"].stops)
    r = s.preview(text="Road between C1 and C2 closed from 10:00 to 10:30 adding 25 min")
    assert r["ok"] and r["requires_confirmation"]
    try:
        s.apply(r["id"]); assert False, "applied without confirmation"
    except Exception as e:
        assert "confirmation" in str(e)
    assert s.plan.routes["V1"].stops == before and s.plan.label == "initial"
    s.apply(r["id"], confirm=True)
    assert s.plan.label != "initial"


def test_text_parser_breakdown_and_urgent():
    s = session()
    r = parse_text("Vehicle V2 broke down at 09:30", s.env, s.plan.now, {})
    assert r["ok"] and r["incident"]["type"] == "vehicle_breakdown"
    r = parse_text("Urgent order to C5, 12 kg, between 10:00 and 11:30, received at 09:45", s.env, s.plan.now, {})
    assert r["ok"] and r["incident"]["data"]["delivery"]["weight"] == 12
    assert not parse_text("Urgent order to C5 asap", s.env, 0, {})["ok"]


def test_invalid_planner_candidate_rejected_and_last_valid_plan_retained():
    def evil(plan, env, inc, strat):
        res = apply_incident(plan, env, inc, strat)
        # sabotage: assign a stop to the failed vehicle and drop another order silently
        res.plan.routes["V1"].stops.append(Stop("D8", "deliver", "C8"))
        return res
    s = session()
    s.planner_override = evil
    last = s.plan
    r = s.preview({"type": "vehicle_breakdown", "vehicle_id": "V1", "time": "09:10"})
    assert r["accepted"] is False and not r["validation"]["valid"]
    try:
        s.apply(r["id"]); assert False
    except Exception:
        pass
    assert s.plan is last


def test_validator_catches_dropped_delivery_and_altered_history():
    s = session()
    plan = s.plan.copy()
    plan.routes["V3"].stops.pop(0)                            # silently drop an order
    rep = validate_plan(plan, s.env)
    assert not rep["valid"] and any("not accounted" in e for e in rep["errors"])
    r = s.preview({"type": "vehicle_breakdown", "vehicle_id": "V1", "time": "09:10"})
    s.apply(r["id"])
    tampered = s.plan.copy()
    tampered.history["V1"][0]["start"] += 10
    rep = validate_plan(tampered, s.env, prior=s.initial_plan, prior_env=s.env0, now=s.plan.now)
    assert not rep["valid"] and any("altered" in e for e in rep["errors"])


def test_incident_in_the_past_rejected():
    s = session()
    s.apply(s.preview({"type": "vehicle_breakdown", "vehicle_id": "V1", "time": "09:10"})["id"])
    r = s.preview({"type": "road_closure", "a": "C1", "b": "C2", "start": "08:00", "end": "08:30", "extra": 5, "time": "08:30"})
    assert not r["ok"]


def test_disruption_that_makes_plan_infeasible_is_reported_honestly():
    s = session()
    r = s.preview({"type": "vehicle_breakdown", "vehicle_id": "V1", "time": "09:10"})
    assert r["summary"]["broken"] > 0                          # not everything can be saved
    assert r["summary"]["kept"] + r["summary"]["moved"] + r["summary"]["broken"] == r["summary"]["total"]


def test_double_failure_cascade_stays_valid():
    s = session()
    s.apply(s.preview({"type": "vehicle_breakdown", "vehicle_id": "V1", "time": "09:10"})["id"])
    r = s.preview({"type": "vehicle_breakdown", "vehicle_id": "V2", "time": "09:50"})
    assert r["validation"]["valid"], r["validation"]["errors"]


def test_scenario_validation():
    d = demo_dict(); d["deliveries"][0]["location"] = "NOPE"
    try:
        Scenario.from_dict(d); assert False
    except ValidationError:
        pass
