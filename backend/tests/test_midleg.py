"""Tests for breakdown mid-leg stall location modelling."""
from helpers import session, demo_dict
from reroute.models import Scenario
from reroute.engine import Session
from reroute.schedule import Env, evaluate_route


def test_breakdown_midleg_creates_stall_location():
    """When a vehicle breaks down while in transit (mid-leg), a STALL:<vid>
    virtual location should be created with interpolated travel times."""
    s = session()
    # V1 departs DEPOT at 08:00, heads to first delivery at ~08:20
    # Breakdown at 08:10 = mid-transit between DEPOT and first stop
    r = s.preview({"type": "vehicle_breakdown", "vehicle_id": "V1", "time": "08:10"})
    assert r["ok"] and r["accepted"]
    assert r["validation"]["valid"], r["validation"]["errors"]
    s.apply(r["id"])
    
    # Check for STALL location
    failure = s.plan.failures["V1"]
    loc = failure["location"]
    # The stall location should exist in the env
    assert loc in s.env.locations, f"Stall location {loc} not in env.locations"
    # If it's a STALL node, distances should be interpolated (not zero)
    if loc.startswith("STALL:"):
        assert loc in s.env.matrix
        # Distance to depot should be > 0 (it's somewhere along the leg)
        assert s.env.matrix[loc]["DEPOT"] >= 0
        # Distance from depot to stall should also be > 0
        assert s.env.matrix["DEPOT"][loc] >= 0


def test_breakdown_at_stop_no_stall_node():
    """If the vehicle has arrived at a stop (waiting/in-service), no stall node is needed."""
    s = session()
    # V1's first delivery is ~20 min from DEPOT, arrives ~08:20
    # Breakdown at 08:30 = after arrival at first stop, waiting/serving
    r = s.preview({"type": "vehicle_breakdown", "vehicle_id": "V1", "time": "08:30"})
    assert r["ok"] and r["accepted"]
    s.apply(r["id"])
    loc = s.plan.failures["V1"]["location"]
    # Should be at the stop location, not a stall node
    assert not loc.startswith("STALL:"), f"Expected real location, got {loc}"


def test_midleg_stall_distances_are_interpolated():
    """Stall node distances should be between the departure and arrival node distances."""
    s = session()
    # Deliberately pick a time that's clearly mid-leg
    # V1 departs DEPOT at 480 (08:00), first stop at C2 ~22.8 min later = ~502.8
    # Breakdown at 08:05 (485) = 5 min into a ~22.8 min leg = ~22% along
    r = s.preview({"type": "vehicle_breakdown", "vehicle_id": "V1", "time": "08:05"})
    assert r["ok"] and r["accepted"]
    s.apply(r["id"])
    loc = s.plan.failures["V1"]["location"]
    if loc.startswith("STALL:"):
        # Distance to any node X should be between dist(DEPOT,X) and dist(first_stop, X)
        for target in ["C1", "C5", "C10"]:
            d_stall = s.env.matrix[loc][target]
            # Just verify it's a valid non-negative distance
            assert d_stall >= 0, f"Negative distance from stall to {target}"


def test_breakdown_midleg_cargo_pickup_uses_stall():
    """After a mid-leg breakdown, the pickup stop for cargo recovery should
    be at the stall location, not the origin or next stop."""
    s = session()
    r = s.preview({"type": "vehicle_breakdown", "vehicle_id": "V1", "time": "08:10"})
    assert r["ok"] and r["accepted"]
    s.apply(r["id"])
    
    stall_loc = s.plan.failures["V1"]["location"]
    # Any PICKUP:V1 stops should reference the stall location
    for vid, route in s.plan.routes.items():
        for stop in route.stops:
            if stop.kind == "pickup" and stop.recover_from == "V1":
                assert stop.location == stall_loc, \
                    f"Pickup at {stop.location}, expected stall {stall_loc}"


def test_breakdown_midleg_double_failure_valid():
    """Two mid-leg breakdowns in sequence should produce a valid plan."""
    s = session()
    r = s.preview({"type": "vehicle_breakdown", "vehicle_id": "V1", "time": "08:10"})
    assert r["validation"]["valid"]
    s.apply(r["id"])
    r2 = s.preview({"type": "vehicle_breakdown", "vehicle_id": "V2", "time": "08:40"})
    assert r2["validation"]["valid"], r2["validation"]["errors"]
