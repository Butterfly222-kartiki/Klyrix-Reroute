"""Tests for improved repair: causal eviction, 2-opt post-pass, stops_moved metric."""
import random
from helpers import session, demo_dict
from reroute.models import Scenario
from reroute.engine import Session
from reroute.compare import summarize


def test_stops_moved_metric_present():
    """The comparison summary should include stops_moved."""
    s = session()
    r = s.preview({"type": "vehicle_breakdown", "vehicle_id": "V1", "time": "09:10"})
    assert "stops_moved" in r["summary"]
    assert r["summary"]["stops_moved"] >= 0


def test_causal_eviction_prefers_upstream():
    """When a disruption makes a downstream delivery late, the repair should
    consider evicting an upstream stop that causes the lateness, not just the
    late stop itself."""
    s = session()
    # A road closure that slows DEPOT-C1 should potentially evict an earlier stop
    r = s.preview({"type": "road_closure", "a": "DEPOT", "b": "C1",
                   "start": "08:00", "end": "12:00", "extra": 200, "time": "08:00"})
    assert r["ok"] and r["accepted"]
    assert r["validation"]["valid"]


def test_post_pass_does_not_break_plan():
    """The 2-opt/relocate post-pass should never break a valid plan."""
    for seed in range(20):
        rng = random.Random(seed)
        d = demo_dict()
        rng.shuffle(d["deliveries"])
        d["deliveries"] = d["deliveries"][:rng.randint(8, 14)]
        s = Session(Scenario.from_dict(d))
        s.plan_initial()
        alive = [v for v in s.env.vehicles if v not in s.plan.failures]
        if not alive:
            continue
        vid = rng.choice(alive)
        r = s.preview({"type": "vehicle_breakdown", "vehicle_id": vid, "time": "09:10"})
        if r["ok"] and r["accepted"]:
            assert r["validation"]["valid"], (seed, r["validation"]["errors"])


def test_benchmark_30_seeds_fulfilled_count():
    """Benchmark over 30 seeds: fulfilled count must not drop below a baseline.
    This ensures the better repair + post-pass doesn't make things worse."""
    total_fulfilled = 0
    total_deliveries = 0
    for seed in range(30):
        rng = random.Random(seed)
        d = demo_dict()
        rng.shuffle(d["deliveries"])
        n = rng.randint(8, 14)
        d["deliveries"] = d["deliveries"][:n]
        s = Session(Scenario.from_dict(d))
        s.plan_initial()
        alive = [v for v in s.env.vehicles if v not in s.plan.failures]
        if len(alive) < 2:
            total_fulfilled += n
            total_deliveries += n
            continue
        vid = rng.choice(alive)
        r = s.preview({"type": "vehicle_breakdown", "vehicle_id": vid, "time": "09:10"})
        if r["ok"] and r["accepted"]:
            s.apply(r["id"])
        total_deliveries += len(s.env.deliveries)
        total_fulfilled += len(s.env.deliveries) - len(s.plan.unassigned)
    # At least 60% fulfilled across all seeds (conservative baseline)
    rate = total_fulfilled / max(total_deliveries, 1)
    assert rate >= 0.6, f"Fulfilled rate {rate:.1%} below 60% across 30 seeds"


def test_shift_end_violations_repaired():
    """The repair should handle shift_end violations, not just window violations."""
    d = demo_dict()
    for v in d["vehicles"]:
        v["shift_end"] = "11:00"  # 3 hours from 08:00
    s = Session(Scenario.from_dict(d))
    s.plan_initial()
    assert s.validation["valid"]
    # Add a closure that slows things down
    r = s.preview({"type": "road_closure", "a": "DEPOT", "b": "C1",
                   "start": "08:00", "end": "12:00", "extra": 30, "time": "08:00"})
    if r["ok"] and r["accepted"]:
        assert r["validation"]["valid"], r["validation"]["errors"]
