import copy
from helpers import demo_dict
from reroute.api_models import (
    IncidentInput,
    TextIncidentInput,
    ApplyInput,
    ScenarioInput,
    SaveInput,
    LoadInput,
    VehicleInput,
    DeliveryInput,
    ClosureInput,
    validate_api_input,
    PYDANTIC_AVAILABLE,
)


def test_save_and_load_input():
    if not PYDANTIC_AVAILABLE:
        return
    # SaveInput defaults to "scenario"
    m, errs = validate_api_input(SaveInput, {})
    assert errs == []
    assert m.name == "scenario"

    m, errs = validate_api_input(SaveInput, {"name": "my_scen"})
    assert errs == []
    assert m.name == "my_scen"

    m, errs = validate_api_input(SaveInput, {"name": "   "})
    assert len(errs) > 0
    assert errs[0]["field"] == "name"

    # LoadInput requires a non-empty name
    m, errs = validate_api_input(LoadInput, {})
    assert len(errs) > 0

    m, errs = validate_api_input(LoadInput, {"name": "demo"})
    assert errs == []
    assert m.name == "demo"


def test_apply_input():
    if not PYDANTIC_AVAILABLE:
        return
    m, errs = validate_api_input(ApplyInput, {"id": "inc-1", "confirm": True})
    assert errs == []
    assert m.id == "inc-1"
    assert m.confirm is True

    m, errs = validate_api_input(ApplyInput, {"confirm": False})
    assert len(errs) > 0
    assert errs[0]["field"] == "id"

    m, errs = validate_api_input(ApplyInput, {"id": "  "})
    assert len(errs) > 0
    assert errs[0]["field"] == "id"


def test_text_incident_input():
    if not PYDANTIC_AVAILABLE:
        return
    m, errs = validate_api_input(TextIncidentInput, {"text": "Road C1 to C2 closed"})
    assert errs == []
    assert m.text == "Road C1 to C2 closed"

    m, errs = validate_api_input(TextIncidentInput, {"text": "   "})
    assert len(errs) > 0
    assert errs[0]["field"] == "text"


def test_incident_input_breakdown():
    if not PYDANTIC_AVAILABLE:
        return
    valid = {"type": "vehicle_breakdown", "vehicle_id": "V1", "time": "09:10"}
    m, errs = validate_api_input(IncidentInput, valid)
    assert errs == []
    assert m.type == "vehicle_breakdown"

    # Missing vehicle_id
    invalid = {"type": "vehicle_breakdown", "time": "09:10"}
    m, errs = validate_api_input(IncidentInput, invalid)
    assert len(errs) > 0
    assert any(e["field"] == "vehicle_id" for e in errs)

    # Missing time
    invalid2 = {"type": "vehicle_breakdown", "vehicle_id": "V1"}
    m, errs = validate_api_input(IncidentInput, invalid2)
    assert len(errs) > 0
    assert any(e["field"] == "time" for e in errs)


def test_incident_input_road_closure():
    if not PYDANTIC_AVAILABLE:
        return
    valid = {
        "type": "road_closure",
        "a": "DEPOT",
        "b": "C10",
        "start": "08:00",
        "end": "09:00",
        "extra": 45,
    }
    m, errs = validate_api_input(IncidentInput, valid)
    assert errs == []

    # End before start
    invalid = copy.deepcopy(valid)
    invalid["start"] = "10:00"
    invalid["end"] = "09:00"
    m, errs = validate_api_input(IncidentInput, invalid)
    assert len(errs) > 0

    # Identical endpoints
    invalid2 = copy.deepcopy(valid)
    invalid2["b"] = "DEPOT"
    m, errs = validate_api_input(IncidentInput, invalid2)
    assert len(errs) > 0


def test_incident_input_urgent_order():
    if not PYDANTIC_AVAILABLE:
        return
    valid = {
        "type": "urgent_order",
        "time": "08:45",
        "delivery": {"location": "C11", "weight": 3, "tw_start": "08:45", "tw_end": "12:00"},
    }
    m, errs = validate_api_input(IncidentInput, valid)
    assert errs == []

    # Invalid weight
    invalid = copy.deepcopy(valid)
    invalid["delivery"]["weight"] = -1
    m, errs = validate_api_input(IncidentInput, invalid)
    assert len(errs) > 0
    assert any(e["field"] == "delivery.weight" for e in errs)


def test_incident_input_unknown_type():
    if not PYDANTIC_AVAILABLE:
        return
    m, errs = validate_api_input(IncidentInput, {"type": "tornado"})
    assert len(errs) > 0
    assert errs[0]["field"] == "type"


def test_scenario_input():
    if not PYDANTIC_AVAILABLE:
        return
    d = demo_dict()
    m, errs = validate_api_input(ScenarioInput, d)
    assert errs == []
    assert m.depot == "DEPOT"

    # Invalid vehicle capacity
    bad_v = copy.deepcopy(d)
    bad_v["vehicles"][0]["capacity"] = -10
    m, errs = validate_api_input(ScenarioInput, bad_v)
    assert len(errs) > 0
    assert any(e["field"] == "vehicles.0.capacity" for e in errs)

    # Invalid delivery time window
    bad_d = copy.deepcopy(d)
    bad_d["deliveries"][0]["tw_start"] = "18:00"
    bad_d["deliveries"][0]["tw_end"] = "09:00"
    m, errs = validate_api_input(ScenarioInput, bad_d)
    assert len(errs) > 0

    # Non-dict data
    m, errs = validate_api_input(ScenarioInput, "not a dict")
    assert len(errs) > 0
