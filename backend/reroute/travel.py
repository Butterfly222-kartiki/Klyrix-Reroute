"""Time-dependent travel model on a simulated road network (no live maps)."""
from __future__ import annotations
import heapq
from typing import Dict, List, Tuple
from .models import Closure

INF = float("inf")

# Module-level cache for Floyd-Warshall base matrices
_FLOYD_CACHE: Dict[Tuple, dict] = {}


def _matrix_key(matrix: Dict[str, Dict[str, float]]) -> Tuple:
    """Create a hashable key from a matrix for caching."""
    items = []
    for a in sorted(matrix.keys()):
        for b in sorted(matrix[a].keys()):
            items.append((a, b, matrix[a][b]))
    return tuple(items)


class TravelModel:
    """Matrix entries are road-edge times. Without closures, travel = all-pairs shortest path
    over the matrix. With closures, time-dependent Dijkstra: an edge's time is increased only if
    the vehicle *enters* it while the closure window is active (FIFO assumption)."""

    def __init__(self, matrix: Dict[str, Dict[str, float]], closures: List[Closure] = ()):
        self.matrix = matrix
        self.nodes = sorted(matrix)
        self.closures = list(closures)
        # Check cache for Floyd-Warshall base matrix
        self._matrix_key = _matrix_key(matrix)
        if self._matrix_key in _FLOYD_CACHE:
            self._base = _FLOYD_CACHE[self._matrix_key]
        else:
            self._base = self._floyd()
            _FLOYD_CACHE[self._matrix_key] = self._base
        self._cache: Dict[tuple, float] = {}

    def _floyd(self):
        d = {a: {} for a in self.nodes}
        # Initialize: diagonal = 0, direct edges from matrix, others = INF
        for i in self.nodes:
            for j in self.nodes:
                if i == j:
                    d[i][j] = 0.0
                elif j in self.matrix.get(i, {}):
                    d[i][j] = self.matrix[i][j]
                else:
                    d[i][j] = INF
        
        # Floyd-Warshall: compute all-pairs shortest paths
        for k in self.nodes:
            for i in self.nodes:
                for j in self.nodes:
                    if d[i][k] + d[k][j] < d[i][j]:
                        d[i][j] = d[i][k] + d[k][j]
        return d

    def with_closures(self, closures: List[Closure]) -> "TravelModel":
        return TravelModel(self.matrix, closures)

    def base(self, a: str, b: str) -> float:
        return self._base[a][b]

    def edge(self, u: str, v: str, t: float) -> float:
        w = self.matrix.get(u, {}).get(v, INF)
        if w == INF:
            return INF
        for c in self.closures:
            if c.matches(u, v) and c.active(t):
                # Check if this is a full closure (blocked=True or extra/factor indicate complete blockage)
                if hasattr(c, 'blocked') and c.blocked:
                    return INF
                w = w * c.factor + c.extra
                # Treat very large penalties as full closure (INF)
                if w >= 999 or c.extra >= 999 or c.factor >= 100:
                    return INF
        return w

    def time(self, a: str, b: str, depart: float) -> float:
        if a == b:
            return 0.0
        if not self.closures:
            return self._base[a][b]
        key = (a, b, round(depart, 4))
        if key in self._cache:
            return self._cache[key]
        dist = {a: depart}
        heap = [(depart, a)]
        while heap:
            t, u = heapq.heappop(heap)
            if u == b:
                break
            if t > dist.get(u, INF):
                continue
            for v in self.nodes:
                if v == u:
                    continue
                edge_time = self.edge(u, v, t)
                if edge_time == INF:
                    continue
                nt = t + edge_time
                if nt < dist.get(v, INF):
                    dist[v] = nt
                    heapq.heappush(heap, (nt, v))
        # If destination not reached, return INF
        if b not in dist:
            self._cache[key] = INF
            return INF
        res = dist[b] - depart
        self._cache[key] = res
        return res
