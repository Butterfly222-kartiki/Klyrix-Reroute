import json, os
from reroute.models import Scenario
from reroute.engine import Session

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def demo_dict():
    return json.load(open(os.path.join(ROOT, "data", "demo_scenario.json")))

def session(mod=None):
    d = demo_dict()
    if mod:
        mod(d)
    s = Session(Scenario.from_dict(d))
    s.plan_initial()
    return s
