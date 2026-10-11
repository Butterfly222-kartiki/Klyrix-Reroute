"""Pydantic v2 API layer wrapping the API boundary for input validation.

Falls back gracefully if Pydantic is not installed so core functionality and tests remain intact.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Union

try:
    import pydantic
    from pydantic import (
        BaseModel,
        ConfigDict,
        Field,
        field_validator,
        model_validator,
        ValidationError as PydanticValidationError,
    )
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    BaseModel = object  # type: ignore
    PydanticValidationError = Exception  # type: ignore

from .models import to_minutes, ValidationError as ModelValidationError


if PYDANTIC_AVAILABLE:

    # -------------------------------------------------------------------------
    # Submodels for Scenario & Incidents
    # -------------------------------------------------------------------------
    class VehicleInput(BaseModel):
        model_config = ConfigDict(extra="allow")

        id: str
        capacity: float
        start_time: Union[float, int, str] = 0.0
        shift_end: Union[float, int, str] = 1440.0

        @field_validator("id")
        @classmethod
        def validate_id(cls, v: str) -> str:
            v = str(v).strip()
            if not v:
                raise ValueError("id cannot be empty")
            return v

        @field_validator("capacity")
        @classmethod
        def validate_capacity(cls, v: float) -> float:
            if v <= 0:
                raise ValueError("capacity must be > 0")
            return v

        @field_validator("start_time", "shift_end")
        @classmethod
        def validate_vtime(cls, v: Union[float, int, str]) -> Union[float, int, str]:
            to_minutes(v)
            return v

        @model_validator(mode="after")
        def validate_shift(self) -> "VehicleInput":
            st = to_minutes(self.start_time)
            se = to_minutes(self.shift_end)
            if se < st:
                raise ValueError("shift_end before start_time")
            return self

    class DeliveryInput(BaseModel):
        model_config = ConfigDict(extra="allow")

        id: Optional[str] = None
        location: str
        weight: float
        tw_start: Union[float, int, str] = 0.0
        tw_end: Union[float, int, str] = 1440.0
        service: float = 5.0
        priority: int = 0
        release_time: Union[float, int, str] = 0.0

        @field_validator("location")
        @classmethod
        def validate_location(cls, v: str) -> str:
            v = str(v).strip()
            if not v:
                raise ValueError("location cannot be empty")
            return v

        @field_validator("weight")
        @classmethod
        def validate_weight(cls, v: float) -> float:
            if v < 0:
                raise ValueError("weight must be >= 0")
            return v

        @field_validator("service")
        @classmethod
        def validate_service(cls, v: float) -> float:
            if v < 0:
                raise ValueError("service must be >= 0")
            return v

        @field_validator("tw_start", "tw_end", "release_time")
        @classmethod
        def validate_dtime(cls, v: Union[float, int, str]) -> Union[float, int, str]:
            to_minutes(v)
            return v

        @model_validator(mode="after")
        def validate_tw(self) -> "DeliveryInput":
            st = to_minutes(self.tw_start)
            en = to_minutes(self.tw_end)
            if en < st:
                raise ValueError("tw_end before tw_start")
            return self

    class ClosureInput(BaseModel):
        model_config = ConfigDict(extra="allow")

        a: str
        b: str
        start: Union[float, int, str]
        end: Union[float, int, str]
        extra: float = 0.0
        factor: float = 1.0
        id: str = ""

        @field_validator("a", "b")
        @classmethod
        def validate_endpoint(cls, v: str) -> str:
            v = str(v).strip()
            if not v:
                raise ValueError("endpoint cannot be empty")
            return v

        @field_validator("start", "end")
        @classmethod
        def validate_ctime(cls, v: Union[float, int, str]) -> Union[float, int, str]:
            to_minutes(v)
            return v

        @field_validator("extra")
        @classmethod
        def validate_extra(cls, v: float) -> float:
            if v < 0:
                raise ValueError("extra must be >= 0")
            return v

        @field_validator("factor")
        @classmethod
        def validate_factor(cls, v: float) -> float:
            if v < 1:
                raise ValueError("factor must be >= 1")
            return v

        @model_validator(mode="after")
        def validate_endpoints_and_times(self) -> "ClosureInput":
            if self.a == self.b:
                raise ValueError("Closure endpoints must differ")
            st = to_minutes(self.start)
            en = to_minutes(self.end)
            if en <= st:
                raise ValueError("Closure end must be after start")
            return self

    # -------------------------------------------------------------------------
    # API Input Models
    # -------------------------------------------------------------------------
    class SaveInput(BaseModel):
        name: str = "scenario"

        @field_validator("name")
        @classmethod
        def validate_name(cls, v: str) -> str:
            v = str(v).strip()
            if not v:
                raise ValueError("name cannot be empty")
            return v

    class LoadInput(BaseModel):
        name: str

        @field_validator("name")
        @classmethod
        def validate_name(cls, v: str) -> str:
            v = str(v).strip()
            if not v:
                raise ValueError("name cannot be empty")
            return v

    class ApplyInput(BaseModel):
        id: str
        confirm: bool = False

        @field_validator("id")
        @classmethod
        def validate_id(cls, v: str) -> str:
            v = str(v).strip()
            if not v:
                raise ValueError("id cannot be empty")
            return v

    class TextIncidentInput(BaseModel):
        text: str

        @field_validator("text")
        @classmethod
        def validate_text(cls, v: str) -> str:
            v = str(v).strip()
            if not v:
                raise ValueError("text cannot be empty")
            return v

    class IncidentInput(BaseModel):
        model_config = ConfigDict(extra="allow")

        type: str
        time: Optional[Union[float, int, str]] = None
        # Road closure
        a: Optional[str] = None
        b: Optional[str] = None
        start: Optional[Union[float, int, str]] = None
        end: Optional[Union[float, int, str]] = None
        extra: Optional[float] = 0.0
        factor: Optional[float] = 1.0
        # Breakdown
        vehicle_id: Optional[str] = None
        # Urgent order
        delivery: Optional[DeliveryInput] = None

        @field_validator("type")
        @classmethod
        def validate_type(cls, v: str) -> str:
            valid_types = {"road_closure", "vehicle_breakdown", "urgent_order"}
            if v not in valid_types:
                raise ValueError(f"Unknown incident type '{v}'. Must be one of: {', '.join(sorted(valid_types))}")
            return v

        @field_validator("time")
        @classmethod
        def validate_inc_time(cls, v: Optional[Union[float, int, str]]) -> Optional[Union[float, int, str]]:
            if v is not None:
                to_minutes(v)
            return v

        @field_validator("start", "end")
        @classmethod
        def validate_inc_interval(cls, v: Optional[Union[float, int, str]]) -> Optional[Union[float, int, str]]:
            if v is not None:
                to_minutes(v)
            return v

        @field_validator("extra")
        @classmethod
        def validate_extra(cls, v: Optional[float]) -> Optional[float]:
            if v is not None and v < 0:
                raise ValueError("extra must be >= 0")
            return v

        @field_validator("factor")
        @classmethod
        def validate_factor(cls, v: Optional[float]) -> Optional[float]:
            if v is not None and v < 1:
                raise ValueError("factor must be >= 1")
            return v

        @model_validator(mode="after")
        def validate_incident_body(self) -> "IncidentInput":
            if self.type == "road_closure":
                if not self.a:
                    raise ValueError("a: Field 'a' is required for road_closure")
                if not self.b:
                    raise ValueError("b: Field 'b' is required for road_closure")
                if self.a == self.b:
                    raise ValueError("Closure endpoints must differ")
                if self.start is None:
                    raise ValueError("start: Field 'start' is required for road_closure")
                if self.end is None:
                    raise ValueError("end: Field 'end' is required for road_closure")
                st = to_minutes(self.start)
                en = to_minutes(self.end)
                if en <= st:
                    raise ValueError("Closure end must be after start")
                extra = self.extra or 0.0
                factor = self.factor or 1.0
                if extra == 0 and factor == 1:
                    raise ValueError("Closure must increase travel time (extra > 0 or factor > 1)")
            elif self.type == "vehicle_breakdown":
                if not self.vehicle_id:
                    raise ValueError("vehicle_id: Field 'vehicle_id' is required for vehicle_breakdown")
                if self.time is None:
                    raise ValueError("time: Field 'time' is required for vehicle_breakdown")
            elif self.type == "urgent_order":
                if self.time is None:
                    raise ValueError("time: Field 'time' is required for urgent_order")
                if self.delivery is None:
                    raise ValueError("delivery: Field 'delivery' is required for urgent_order")
                if self.delivery.weight <= 0:
                    raise ValueError("delivery.weight: Urgent order delivery weight must be > 0")
            return self

    class ScenarioInput(BaseModel):
        model_config = ConfigDict(extra="allow")

        name: str = "scenario"
        depot: str
        locations: Union[Dict[str, Any], List[str]]
        matrix: Dict[str, Dict[str, float]]
        vehicles: List[VehicleInput]
        deliveries: List[DeliveryInput]
        closures: List[ClosureInput] = Field(default_factory=list)
        transfer_minutes: float = 5.0

        @field_validator("depot")
        @classmethod
        def validate_depot(cls, v: str) -> str:
            v = str(v).strip()
            if not v:
                raise ValueError("depot cannot be empty")
            return v

        @field_validator("vehicles")
        @classmethod
        def validate_vehicles(cls, v: List[VehicleInput]) -> List[VehicleInput]:
            if not v:
                raise ValueError("At least one vehicle required")
            vids = [x.id for x in v]
            if len(vids) != len(set(vids)):
                raise ValueError("Duplicate vehicle ids")
            return v

        @field_validator("deliveries")
        @classmethod
        def validate_deliveries(cls, v: List[DeliveryInput]) -> List[DeliveryInput]:
            for d in v:
                if not d.id or not str(d.id).strip():
                    raise ValueError("Delivery id cannot be empty")
            dids = [x.id for x in v]
            if len(dids) != len(set(dids)):
                raise ValueError("Duplicate delivery ids")
            return v

        @model_validator(mode="after")
        def validate_scenario(self) -> "ScenarioInput":
            loc_names = set(self.locations if isinstance(self.locations, list) else self.locations.keys())
            if self.depot not in loc_names:
                raise ValueError(f"depot: Depot '{self.depot}' is not in locations")
            for d in self.deliveries:
                if d.location not in loc_names:
                    raise ValueError(f"deliveries: Delivery {d.id}: unknown location '{d.location}'")
            for c in self.closures:
                if c.a not in loc_names or c.b not in loc_names:
                    raise ValueError(f"closures: Closure references unknown location: '{c.a}' or '{c.b}'")
            for a, row in self.matrix.items():
                for b, w in row.items():
                    if float(w) < 0:
                        raise ValueError(f"matrix.{a}.{b}: Negative travel time {a}->{b}")
            return self

else:
    # Fallback placeholders when Pydantic is not installed
    class VehicleInput: pass       # type: ignore
    class DeliveryInput: pass      # type: ignore
    class ClosureInput: pass       # type: ignore
    class SaveInput: pass          # type: ignore
    class LoadInput: pass          # type: ignore
    class ApplyInput: pass         # type: ignore
    class TextIncidentInput: pass  # type: ignore
    class IncidentInput: pass      # type: ignore
    class ScenarioInput: pass      # type: ignore


# -----------------------------------------------------------------------------
# Validation Helper
# -----------------------------------------------------------------------------
def validate_api_input(model_class: Any, data: Any) -> tuple[Any, List[Dict[str, str]]]:
    """Validate input data against a Pydantic model class.

    Returns:
        (parsed_model, []) on success
        (None, [{"field": "path.to.field", "error": "message"}, ...]) on validation error
    """
    if not PYDANTIC_AVAILABLE:
        # Pydantic is not installed; bypass schema validation gracefully
        return (data, [])

    if not isinstance(data, dict):
        return (None, [{"field": "", "error": "Expected JSON object"}])

    try:
        model = model_class.model_validate(data)
        return (model, [])
    except PydanticValidationError as e:
        errors = []
        for err in e.errors():
            loc = err.get("loc", ())
            field_path = ".".join(str(p) for p in loc)
            msg = err.get("msg", "")
            if msg.startswith("Value error, "):
                msg = msg[len("Value error, "):]
            if not field_path and ":" in msg:
                prefix, rest = msg.split(":", 1)
                if " " not in prefix:
                    field_path = prefix.strip()
                    msg = rest.strip()
            errors.append({"field": field_path, "error": msg})
        return (None, errors)
