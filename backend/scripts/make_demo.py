"""Generate data/demo_scenario.json (deterministic). Matrix = Euclidean distance * 0.6 min/unit."""
import json, math, os
pts = {"DEPOT": (50, 50), "C1": (22, 70), "C2": (35, 85), "C3": (60, 88), "C4": (82, 75), "C5": (90, 55),
       "C6": (85, 30), "C7": (65, 12), "C8": (40, 15), "C9": (15, 30), "C10": (10, 52), "C11": (48, 68), "C12": (70, 45)}
names = list(pts)
matrix = {a: {b: round(math.dist(pts[a], pts[b]) * 0.6, 1) for b in names} for a in names}
H = lambda h, m=0: h * 60 + m
dl = [  # id, loc, weight, window start, window end
    ("D1", "C1", 14, H(8, 30), H(10, 0)), ("D2", "C2", 10, H(8, 30), H(11, 0)), ("D3", "C3", 18, H(9, 0), H(11, 30)),
    ("D4", "C4", 12, H(9, 0), H(10, 30)), ("D5", "C5", 16, H(9, 30), H(12, 0)), ("D6", "C6", 9, H(9, 30), H(11, 0)),
    ("D7", "C7", 20, H(10, 0), H(12, 30)), ("D8", "C8", 11, H(10, 0), H(12, 0)), ("D9", "C9", 15, H(8, 30), H(10, 30)),
    ("D10", "C10", 13, H(9, 0), H(11, 30)), ("D11", "C11", 8, H(8, 30), H(9, 45)), ("D12", "C12", 17, H(9, 30), H(11, 0)),
    ("D13", "C4", 10, H(11, 0), H(13, 0)), ("D14", "C9", 12, H(11, 0), H(13, 30))]
sc = {"name": "Demo - Pune-style metro day (synthetic)", "depot": "DEPOT",
      "locations": {n: {"x": p[0], "y": p[1]} for n, p in pts.items()}, "matrix": matrix,
      "vehicles": [{"id": "V1", "capacity": 70, "start_time": "08:00"}, {"id": "V2", "capacity": 65, "start_time": "08:00"},
                   {"id": "V3", "capacity": 60, "start_time": "08:00"}],
      "deliveries": [{"id": i, "location": l, "weight": w, "tw_start": a, "tw_end": b, "service": 6} for i, l, w, a, b in dl],
      "closures": [], "transfer_minutes": 5}
os.makedirs("data", exist_ok=True)
json.dump(sc, open("data/demo_scenario.json", "w"), indent=1)
print("written", len(dl), "deliveries")
