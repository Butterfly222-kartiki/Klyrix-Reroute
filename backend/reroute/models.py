"""Domain models + validation (stdlib dataclasses; swap for Pydantic later - see README)."""
from __future__ import annotations
import copy, re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

EPS = 1e-6


class ValidationError(ValueError):
    """Raised when structured input is invalid."""


def to_minutes(v: Any) -> float:
    """Accept minutes since midnight (number) or 'HH:MM' / '10am' / '10:30 pm'."""
    if isinstance(v, bool):
        raise ValidationError(f"Invalid time: {v!r}")
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().lower()
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", s)
    if not m:
        try:
            return float(s)
        except ValueError:
            raise ValidationError(f"Invalid time: {v!r}")
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    if mi > 59:
        raise ValidationError(f"Invalid time: {v!r}")
    return float(h * 60 + mi)


def fmt_time(m: Optional[float]) -> str:
    if m is None:
        return "--:--"
    m = int(round(m))
    return f"{m // 60:02d}:{m % 60:02d}"


@dataclass
class Vehicle:
    id: str
    capacity: float
    start_time: float = 0.0
    shift_end: float = 1440.0     # must return to depot by this time (default: midnight)

    @classmethod
    def from_dict(cls, d: dict) -> "Vehicle":
        v = cls(str(d["id"]), float(d["capacity"]), to_minutes(d.get("start_time", 0)),
                to_minutes(d.get("shift_end", 1440)))
        if v.capacity <= 0:
            raise ValidationError(f"Vehicle {v.id}: capacity must be > 0")
        if v.shift_end < v.start_time:
            raise ValidationError(f"Vehicle {v.id}: shift_end before start_time")
        return v


@dataclass
class Delivery:
    id: str
    location: str
    weight: float
    tw_start: float
    tw_end: float
    service: float = 5.0
    priority: int = 0          # 1 = urgent
    release_time: float = 0.0  # earliest time the parcel exists (urgent orders)

    @classmethod
    def from_dict(cls, d: dict) -> "Delivery":
        x = cls(
            str(d["id"]), str(d["location"]), float(d["weight"]),
            to_minutes(d.get("tw_start", 0)), to_minutes(d.get("tw_end", 24 * 60)),
            float(d.get("service", 5)), int(d.get("priority", 0)),
            to_minutes(d.get("release_time", 0)),
        )
        if x.weight < 0 or x.service < 0:
            raise ValidationError(f"Delivery {x.id}: weight/service must be >= 0")
        if x.tw_end < x.tw_start:
            raise ValidationError(f"Delivery {x.id}: tw_end before tw_start")
        return x


@dataclass
class Closure:
    a: str
    b: str
    start: float
    end: float
    extra: float = 0.0   # minutes added to the edge while active
    factor: float = 1.0  # multiplier applied before `extra`
    blocked: bool = False  # if True, edge is completely impassable (inf)
    id: str = ""

    def matches(self, u: str, v: str) -> bool:
        return (u == self.a and v == self.b) or (u == self.b and v == self.a)

    def active(self, t: float) -> bool:
        return self.start <= t < self.end

    @classmethod
    def from_dict(cls, d: dict) -> "Closure":
        c = cls(str(d["a"]), str(d["b"]), to_minutes(d["start"]), to_minutes(d["end"]),
                float(d.get("extra", 0)), float(d.get("factor", 1)),
                bool(d.get("blocked", False)), str(d.get("id", "")))
        if c.end <= c.start:
            raise ValidationError("Closure end must be after start")
        if not c.blocked and (c.extra < 0 or c.factor < 1):
            raise ValidationError("Closure may only increase travel time")
        return c


@dataclass
class Scenario:
    name: str
    depot: str
    locations: Dict[str, dict]
    matrix: Dict[str, Dict[str, float]]
    vehicles: List[Vehicle]
    deliveries: List[Delivery]
    closures: List[Closure] = field(default_factory=list)
    transfer_minutes: float = 5.0   # time to transfer cargo from a broken-down vehicle

    @classmethod
    def from_dict(cls, d: dict) -> "Scenario":
        try:
            locs = d["locations"]
            if isinstance(locs, list):
                locs = {str(n): {} for n in locs}
            matrix = {a: {b: float(w) for b, w in row.items()} for a, row in d["matrix"].items()}
            s = cls(d.get("name", "scenario"), str(d["depot"]), dict(locs), matrix,
                    [Vehicle.from_dict(v) for v in d["vehicles"]],
                    [Delivery.from_dict(x) for x in d["deliveries"]],
                    [Closure.from_dict(c) for c in d.get("closures", [])],
                    float(d.get("transfer_minutes", 5)))
        except KeyError as e:
            raise ValidationError(f"Missing field: {e}")
        s.validate()
        return s

    def validate(self) -> None:
        if self.depot not in self.locations:
            raise ValidationError("Depot is not in locations")
        names = list(self.locations)
        for a in names:  # fill symmetric entries, zero diagonal
            self.matrix.setdefault(a, {})
            self.matrix[a][a] = 0.0
        for a in names:
            for b in names:
                if b not in self.matrix[a]:
                    if a in self.matrix.get(b, {}):
                        self.matrix[a][b] = self.matrix[b][a]
                    else:
                        raise ValidationError(f"Travel time {a}->{b} missing")
                if self.matrix[a][b] < 0:
                    raise ValidationError(f"Negative travel time {a}->{b}")
        for tbl, items in (("vehicle", self.vehicles), ("delivery", self.deliveries)):
            ids = [i.id for i in items]
            if len(ids) != len(set(ids)):
                raise ValidationError(f"Duplicate {tbl} ids")
        if not self.vehicles:
            raise ValidationError("At least one vehicle required")
        for d in self.deliveries:
            if d.location not in self.locations:
                raise ValidationError(f"Delivery {d.id}: unknown location {d.location}")
        for c in self.closures:
            if c.a not in self.locations or c.b not in self.locations:
                raise ValidationError("Closure references unknown location")

    def to_dict(self) -> dict:
        return {"name": self.name, "depot": self.depot, "locations": self.locations,
                "matrix": self.matrix, "vehicles": [asdict(v) for v in self.vehicles],
                "deliveries": [asdict(d) for d in self.deliveries],
                "closures": [asdict(c) for c in self.closures],
                "transfer_minutes": self.transfer_minutes}

    def copy(self) -> "Scenario":
        return copy.deepcopy(self)
