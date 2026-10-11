"""Tests for widened text interpreter patterns and NetworkX graph features."""
from helpers import session, demo_dict
from reroute.incidents import parse_text, _resolve_vehicle
from reroute.schedule import Env
from reroute.models import Scenario


def test_closed_between_time_format():
    """'closed between 10 and 10:30' should parse the time range."""
    s = session()
    r = parse_text("Road between C1 and C2 closed between 10:00 and 10:30 adding 25 min",
                   s.env, s.plan.now, {})
    assert r["ok"], r["errors"]
    assert r["incident"]["type"] == "road_closure"


def test_truck_alias():
    """'Truck 2' should resolve to V2."""
    s = session()
    r = parse_text("Truck 2 broke down at 09:30", s.env, s.plan.now, {})
    assert r["ok"], r["errors"]
    assert r["incident"]["data"]["vehicle_id"] == "V2"


def test_truck_alias_resolve():
    """_resolve_vehicle should handle aliases."""
    s = session()
    assert _resolve_vehicle("V1", s.env) == "V1"
    assert _resolve_vehicle("truck 2", s.env) == "V2"
    assert _resolve_vehicle("Van 3", s.env) == "V3"
    assert _resolve_vehicle("Truck 99", s.env) is None


def test_reversed_order_closure():
    """'Blocked road between X and Y' (reversed order) should parse."""
    s = session()
    r = parse_text("Blocked road between C3 and C4 from 10:00 to 11:00 adding 20 min",
                   s.env, s.plan.now, {})
    assert r["ok"], r["errors"]
    assert r["incident"]["type"] == "road_closure"


def test_simple_closure_format():
    """'C1 to C2 is closed from 10:00 to 10:30' should parse."""
    s = session()
    r = parse_text("C1 to C2 is closed from 10:00 to 10:30", s.env, s.plan.now, {})
    assert r["ok"], r["errors"]
    assert r["incident"]["type"] == "road_closure"


def test_time_range_without_from():
    """'10:00 to 10:30' without 'from' prefix should parse as a time range."""
    s = session()
    r = parse_text("Road between C1 and C2 closed 10:00 to 10:30",
                   s.env, s.plan.now, {})
    assert r["ok"], r["errors"]


def test_multiple_incidents_semicolon():
    """Multiple incidents separated by semicolons should be parsed as separate incidents."""
    s = session()
    r = parse_text("Road between C1 and C2 closed from 10:00 to 10:30; Vehicle V1 broke down at 09:10",
                   s.env, s.plan.now, {})
    assert r["ok"], r["errors"]
    # Should return multiple incidents
    assert "incidents" in r
    assert len(r["incidents"]) == 2
    # First incident is the closure
    assert r["incidents"][0]["type"] == "road_closure"
    # Second incident is the breakdown
    assert r["incidents"][1]["type"] == "vehicle_breakdown"


def test_vehicle_stopped_pattern():
    """'Vehicle V1 stopped at 09:10' should parse as breakdown."""
    s = session()
    r = parse_text("Vehicle V1 stopped at 09:10", s.env, s.plan.now, {})
    # 'stopped' is now recognized
    assert r["ok"], r["errors"]
    assert r["incident"]["type"] == "vehicle_breakdown"


def test_rush_delivery_pattern():
    """'Rush delivery to C5, 12 kg, between 10:00 and 11:30' should parse."""
    s = session()
    r = parse_text("Rush delivery to C5, 12 kg, between 10:00 and 11:30", s.env, s.plan.now, {})
    assert r["ok"], r["errors"]
    assert r["incident"]["type"] == "urgent_order"


# --- NetworkX graph tests ---

def test_networkx_from_scenario():
    """to_networkx should build a graph from a scenario."""
    from reroute.graph import to_networkx
    s = Scenario.from_dict(demo_dict())
    g = to_networkx(s)
    assert len(g.nodes) == len(s.locations)
    assert g.has_edge("DEPOT", "C1")


def test_sparse_edges_to_matrix():
    """from_edges should derive a full shortest-path matrix from sparse edges."""
    from reroute.graph import from_edges
    locations = {"A": {}, "B": {}, "C": {}, "D": {}}
    edges = [
        {"a": "A", "b": "B", "minutes": 10},
        {"a": "B", "b": "C", "minutes": 15},
        {"a": "C", "b": "D", "minutes": 20},
        {"a": "A", "b": "D", "minutes": 50},
    ]
    matrix = from_edges(locations, edges)
    # Direct: A->B = 10
    assert abs(matrix["A"]["B"] - 10) < 1e-6
    # Shortest path: A->C = A->B->C = 25 (shorter than A->D->C = 50+20)
    assert abs(matrix["A"]["C"] - 25) < 1e-6
    # A->D: direct 50 vs A->B->C->D = 45; should take 45
    assert abs(matrix["A"]["D"] - 45) < 1e-6
    # Diagonal = 0
    assert matrix["A"]["A"] == 0.0


def test_sparse_edges_disconnected():
    """from_edges should raise ValueError for disconnected graphs."""
    from reroute.graph import from_edges
    locations = {"A": {}, "B": {}, "C": {}}
    edges = [{"a": "A", "b": "B", "minutes": 10}]  # C is disconnected
    try:
        from_edges(locations, edges)
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "No path" in str(e) or "disconnected" in str(e).lower()


def test_scenario_from_edges():
    """scenario_from_edges should build a valid scenario from sparse edges."""
    from reroute.graph import scenario_from_edges
    data = {
        "name": "sparse",
        "depot": "A",
        "locations": {"A": {"x": 0, "y": 0}, "B": {"x": 1, "y": 0}, "C": {"x": 1, "y": 1}},
        "edges": [
            {"a": "A", "b": "B", "minutes": 10},
            {"a": "B", "b": "C", "minutes": 15},
            {"a": "A", "b": "C", "minutes": 30},
        ],
        "vehicles": [{"id": "V1", "capacity": 50, "start_time": 0}],
        "deliveries": [{"id": "D1", "location": "B", "weight": 5, "tw_start": 0, "tw_end": 1440}],
    }
    result = scenario_from_edges(data)
    assert "matrix" in result
    assert "edges" not in result
    # Should be a valid scenario
    s = Scenario.from_dict(result)
    assert s.matrix["A"]["B"] == 10


def test_render_graph_svg():
    """render_graph_svg should produce valid SVG."""
    from reroute.graph import render_graph_svg
    s = Scenario.from_dict(demo_dict())
    svg = render_graph_svg(s)
    assert svg.startswith("<svg")
    assert "DEPOT" in svg
    assert "</svg>" in svg
