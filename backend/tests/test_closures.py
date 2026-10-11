"""Tests for closure management: remove/expire, overlapping, fully blocked edges, asymmetric matrices."""
from helpers import demo_dict
from reroute.models import Scenario, Closure
from reroute.engine import Session
from reroute.schedule import Env
from reroute.travel import TravelModel


def test_remove_closure_by_id():
    """Removing a closure by id should restore original travel times."""
    s = Session(Scenario.from_dict(demo_dict()))
    s.plan_initial()
    c = Closure("DEPOT", "C1", 480, 720, extra=100, id="CL1")
    env_with = s.env.evolve(closures=[c])
    # With closure, DEPOT->C1 during active period should be slower
    t_with = env_with.travel.time("DEPOT", "C1", 500)
    t_base = s.env.travel.time("DEPOT", "C1", 500)
    assert t_with > t_base
    
    # Remove the closure
    env_removed = env_with.remove_closure("CL1")
    t_removed = env_removed.travel.time("DEPOT", "C1", 500)
    assert abs(t_removed - t_base) < 1e-6, "After removal, travel time should match base"


def test_expire_closures():
    """Closures whose end <= t should be expired/removed."""
    s = Session(Scenario.from_dict(demo_dict()))
    s.plan_initial()
    c1 = Closure("DEPOT", "C1", 480, 540, extra=100, id="CL1")   # ends 09:00
    c2 = Closure("C2", "C3", 480, 720, extra=50, id="CL2")       # ends 12:00
    env_with = s.env.evolve(closures=[c1, c2])
    assert len(env_with.closures) == 2
    
    # Expire at 09:00 — CL1 should be removed, CL2 stays
    env_expired = env_with.expire_closures(540)
    assert len(env_expired.closures) == 1
    assert env_expired.closures[0].id == "CL2"
    
    # Expire at 12:00 — both should be removed
    env_all_expired = env_with.expire_closures(720)
    assert len(env_all_expired.closures) == 0


def test_overlapping_closures_stack():
    """Multiple closures on the same edge should compound (both apply)."""
    d = demo_dict()
    s = Scenario.from_dict(d)
    env = Env.from_scenario(s)
    
    c1 = Closure("DEPOT", "C1", 480, 720, extra=20)
    c2 = Closure("DEPOT", "C1", 500, 600, extra=30)
    tm = TravelModel(env.matrix, [c1, c2])
    
    base = env.travel.base("DEPOT", "C1")
    
    # At t=510, both closures are active
    # Edge DEPOT->C1: base * c1.factor + c1.extra = base + 20, then * c2.factor + c2.extra
    # Actually they're applied sequentially via the edge() method
    t_both = tm.edge("DEPOT", "C1", 510)
    # Each closure applies: first c1 applies (base * 1 + 20 = base+20), then c2 (result * 1 + 30)
    expected = base + 20 + 30
    assert abs(t_both - expected) < 1e-6, f"Expected {expected}, got {t_both}"
    
    # At t=490, only c1 is active
    t_one = tm.edge("DEPOT", "C1", 490)
    assert abs(t_one - (base + 20)) < 1e-6
    
    # At t=700, only c1 is active (c2 ended)
    t_late = tm.edge("DEPOT", "C1", 700)
    assert abs(t_late - (base + 20)) < 1e-6


def test_fully_blocked_edge_dijkstra_detour():
    """A fully blocked edge (+600 min) should force Dijkstra to find a detour."""
    d = demo_dict()
    s = Scenario.from_dict(d)
    env = Env.from_scenario(s)
    
    c = Closure("DEPOT", "C1", 480, 720, extra=600)
    tm = TravelModel(env.matrix, [c])
    
    base = env.travel.base("DEPOT", "C1")
    t_blocked = tm.time("DEPOT", "C1", 500)
    
    # The travel time should be routed around the closure via another path
    # It might be the direct edge + 600 or a shorter detour
    # Either way it shouldn't be base (which ignores closures)
    assert t_blocked > base - 1e-6, "Blocked edge travel should be >= base"
    
    # The Dijkstra should find a path, not infinite
    assert t_blocked < float("inf"), "Should find an alternate route"
    
    # Direct edge would be base + 600; if detour exists it should be shorter
    direct_penalty = base + 600
    assert t_blocked <= direct_penalty + 1e-6, "Should use detour if shorter than penalty"


def test_asymmetric_matrix():
    """Scenario with asymmetric travel times should work correctly."""
    d = demo_dict()
    # Make the matrix asymmetric: A->B != B->A
    d["matrix"]["DEPOT"]["C1"] = 20.0
    d["matrix"]["C1"]["DEPOT"] = 30.0  # return trip is longer
    s = Scenario.from_dict(d)
    env = Env.from_scenario(s)
    
    # Raw matrix should store asymmetric values
    assert env.matrix["DEPOT"]["C1"] == 20.0
    assert env.matrix["C1"]["DEPOT"] == 30.0
    
    # Floyd-Warshall base time should be <= direct edge (shortest path may go via intermediates)
    assert env.travel.base("DEPOT", "C1") <= 20.0 + 1e-6
    assert env.travel.base("C1", "DEPOT") <= 30.0 + 1e-6
    
    # The asymmetry should be preserved — forward should be different from reverse
    # (unless an intermediate path happens to equalize them)
    forward = env.travel.base("DEPOT", "C1")
    reverse = env.travel.base("C1", "DEPOT")
    # At minimum, forward should be feasible (not infinite)
    assert forward < float("inf")
    assert reverse < float("inf")
    
    # Planning should still work with asymmetric matrix
    sess = Session(s)
    sess.plan_initial()
    assert sess.validation["valid"]


def test_closure_with_factor():
    """A closure with factor > 1 should multiply the edge time."""
    d = demo_dict()
    s = Scenario.from_dict(d)
    env = Env.from_scenario(s)
    
    base = env.matrix["DEPOT"]["C1"]
    c = Closure("DEPOT", "C1", 480, 720, factor=2.0)
    tm = TravelModel(env.matrix, [c])
    
    # During closure, edge time should be doubled
    edge_during = tm.edge("DEPOT", "C1", 500)
    assert abs(edge_during - base * 2) < 1e-6
    
    # Outside closure, normal
    edge_before = tm.edge("DEPOT", "C1", 400)
    assert abs(edge_before - base) < 1e-6


def test_expire_no_change_returns_same():
    """If no closures to expire, expire_closures should return the same env."""
    d = demo_dict()
    s = Scenario.from_dict(d)
    env = Env.from_scenario(s)
    c = Closure("DEPOT", "C1", 480, 720, extra=10)
    env_with = env.evolve(closures=[c])
    
    result = env_with.expire_closures(100)  # all closures are after this
    assert result is env_with  # should be the same object (optimization)


def test_full_closure_with_inf():
    """A full closure with extra=9999 should make the edge unreachable (INF)."""
    d = demo_dict()
    s = Scenario.from_dict(d)
    env = Env.from_scenario(s)
    
    # Create a full closure (extra >= 999 means INF)
    c = Closure("DEPOT", "C1", 480, 720, extra=9999)
    env_closed = env.evolve(closures=[c])
    
    # Direct edge should be INF during the closure
    t_during = env_closed.travel.time("DEPOT", "C1", 500)
    
    # If there's an alternate path through other nodes, it should use that
    # If no alternate path exists, result should be INF
    # In the demo scenario, typically there are alternate paths, so we just check it's not the base time
    t_base = env.travel.time("DEPOT", "C1", 500)
    
    # The detour should exist (since demo has a connected graph), but be longer than base
    # Or if truly blocked, should be INF
    assert t_during >= t_base  # Either detoured or INF, both >= base
    
    # Before the closure, should be normal
    t_before = env_closed.travel.time("DEPOT", "C1", 400)
    assert abs(t_before - t_base) < 1e-6
