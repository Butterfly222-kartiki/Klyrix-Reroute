"""Optional NetworkX view of the road network (used for visualisation / future shortest-path modelling)."""
from __future__ import annotations
from typing import Dict, List, Optional


def to_networkx(scenario):
    """Build a NetworkX graph from a scenario (full matrix)."""
    import networkx as nx
    g = nx.DiGraph()
    for n, attrs in scenario.locations.items():
        g.add_node(n, **attrs)
    names = list(scenario.locations)
    for a in names:
        for b in names:
            if a != b and scenario.matrix.get(a, {}).get(b, 0) > 0:
                g.add_edge(a, b, minutes=scenario.matrix[a][b])
    return g


def from_edges(locations: Dict[str, dict], edges: List[dict], depot: str = "DEPOT") -> Dict[str, Dict[str, float]]:
    """Given a sparse edge list [{a, b, minutes, ?directed}], derive a full shortest-path
    matrix using NetworkX.  Missing direct connections are filled via shortest paths.
    Raises ValueError if the graph is disconnected."""
    import networkx as nx
    g = nx.DiGraph()
    for n, attrs in locations.items():
        g.add_node(n, **attrs)
    for e in edges:
        a, b, m = str(e["a"]), str(e["b"]), float(e["minutes"])
        g.add_edge(a, b, minutes=m)
        if not e.get("directed", False):
            g.add_edge(b, a, minutes=m)
    # Compute all-pairs shortest path lengths
    names = sorted(locations)
    try:
        lengths = dict(nx.all_pairs_dijkstra_path_length(g, weight="minutes"))
    except nx.NetworkXError as exc:
        raise ValueError(f"Cannot compute shortest paths: {exc}")
    matrix: Dict[str, Dict[str, float]] = {}
    for a in names:
        matrix[a] = {}
        for b in names:
            if a == b:
                matrix[a][b] = 0.0
            elif b in lengths.get(a, {}):
                matrix[a][b] = lengths[a][b]
            else:
                raise ValueError(f"No path from {a} to {b} — graph may be disconnected")
    return matrix


def scenario_from_edges(data: dict) -> dict:
    """Build a scenario dict from a sparse-edge format.  Accepts:
    {locations, edges, depot, vehicles, deliveries, ...}
    where `edges` replaces `matrix`.  Returns a dict with `matrix` filled in."""
    locs = data["locations"]
    if isinstance(locs, list):
        locs = {str(n): {} for n in locs}
    matrix = from_edges(locs, data["edges"], data.get("depot", "DEPOT"))
    out = dict(data)
    out["locations"] = locs
    out["matrix"] = matrix
    out.pop("edges", None)
    return out


def render_graph_svg(scenario, routes=None, width: int = 600, height: int = 400) -> str:
    """Render the network as an SVG string using location coordinates."""
    locs = scenario.locations if hasattr(scenario, 'locations') else scenario.get("locations", {})
    depot = scenario.depot if hasattr(scenario, 'depot') else scenario.get("depot", "DEPOT")
    
    # Get coordinate bounds
    xs = [v.get("x", 50) for v in locs.values()]
    ys = [v.get("y", 50) for v in locs.values()]
    if not xs:
        return "<svg></svg>"
    pad = 40
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    x_range = max(x_max - x_min, 1)
    y_range = max(y_max - y_min, 1)
    
    def tx(x):
        return pad + (x - x_min) / x_range * (width - 2 * pad)
    def ty(y):
        return pad + (1 - (y - y_min) / y_range) * (height - 2 * pad)
    
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">']
    parts.append('<style>text{font:11px sans-serif;} .depot{fill:#e74c3c;} .loc{fill:#3498db;} .edge{stroke:#ccc;stroke-width:1;}</style>')
    
    # Draw edges from matrix (only shortest paths)
    matrix = scenario.matrix if hasattr(scenario, 'matrix') else scenario.get("matrix", {})
    names = list(locs)
    drawn = set()
    for a in names:
        for b in names:
            if a < b and matrix.get(a, {}).get(b, 0) > 0:
                key = (min(a, b), max(a, b))
                if key not in drawn:
                    drawn.add(key)
                    ax, ay = tx(locs[a].get("x", 50)), ty(locs[a].get("y", 50))
                    bx, by = tx(locs[b].get("x", 50)), ty(locs[b].get("y", 50))
                    parts.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" class="edge"/>')
    
    # Draw route paths
    colors = ["#e74c3c", "#2ecc71", "#3498db", "#f39c12", "#9b59b6"]
    if routes:
        for idx, (vid, stops) in enumerate(routes.items()):
            color = colors[idx % len(colors)]
            path_locs = stops
            for i in range(len(path_locs) - 1):
                a, b = path_locs[i], path_locs[i + 1]
                if a in locs and b in locs:
                    ax, ay = tx(locs[a].get("x", 50)), ty(locs[a].get("y", 50))
                    bx, by = tx(locs[b].get("x", 50)), ty(locs[b].get("y", 50))
                    parts.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="{color}" stroke-width="2.5" opacity="0.7"/>')
    
    # Draw nodes
    for name, attrs in locs.items():
        cx, cy = tx(attrs.get("x", 50)), ty(attrs.get("y", 50))
        cls = "depot" if name == depot else "loc"
        r = 6 if name == depot else 4
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" class="{cls}"/>')
        parts.append(f'<text x="{cx + 7:.1f}" y="{cy + 4:.1f}">{name}</text>')
    
    parts.append('</svg>')
    return '\n'.join(parts)
