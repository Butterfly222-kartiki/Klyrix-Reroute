"""Randomised invariant tests: whatever the incident, a published plan must be valid and fully accounted."""
import random
from helpers import demo_dict
from reroute.models import Scenario, fmt_time
from reroute.engine import Session


def _rand_incident(rng, s):
    now = s.plan.now
    t = now + rng.choice([0, 10, 25, 40, 60])
    kind = rng.choice(["road_closure", "vehicle_breakdown", "urgent_order"])
    locs = [l for l in s.env.locations if l != "DEPOT"]
    if kind == "road_closure":
        a, b = rng.sample(list(s.env.locations), 2)
        return {"type": kind, "a": a, "b": b, "start": t, "end": t + rng.choice([20, 60, 120]), "extra": rng.choice([10, 30, 90]), "time": t}
    if kind == "vehicle_breakdown":
        alive = [v for v in s.env.vehicles if v not in s.plan.failures]
        return {"type": kind, "vehicle_id": rng.choice(alive), "time": t}
    return {"type": kind, "time": t, "delivery": {"location": rng.choice(locs), "weight": rng.choice([2, 8, 30, 90]),
            "tw_start": t, "tw_end": t + rng.choice([20, 60, 180])}}


def test_random_incident_sequences_stay_valid():
    for seed in range(40):
        rng = random.Random(seed)
        d = demo_dict()
        rng.shuffle(d["deliveries"])
        d["deliveries"] = d["deliveries"][: rng.randint(6, 14)]
        s = Session(Scenario.from_dict(d)); s.plan_initial()
        for _ in range(rng.randint(1, 4)):
            if len(s.plan.failures) >= len(s.env.vehicles) - 0 and rng.random() < .5:
                break
            alive = [v for v in s.env.vehicles if v not in s.plan.failures]
            if not alive:
                break
            r = s.preview(_rand_incident(rng, s))
            if not r["ok"]:
                continue
            assert r["accepted"], (seed, r["attempts"])
            assert r["validation"]["valid"], (seed, r["validation"]["errors"])
            assert sum(r["summary"][k] for k in ("kept", "moved", "broken", "new")) == len(s.env.deliveries) + (1 if r["incident"]["type"] == "urgent_order" else 0)
            for row in r["comparison"]:
                assert row["reason"]
            s.apply(r["id"])
            assert s.validation["valid"]
