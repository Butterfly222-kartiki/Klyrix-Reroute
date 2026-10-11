"""Tests for Pandas export tables, CSV/Excel export, and /api/export endpoint."""
from __future__ import annotations
import json
from helpers import session
from reroute.export import (
    HAS_PANDAS,
    plan_table,
    comparison_table,
    unfulfilled_table,
    export_csv,
    export_excel,
)
import reroute.server as server


def test_plan_table_has_correct_columns():
    if not HAS_PANDAS:
        return
    s = session()
    df = plan_table(s.plan, s.env)
    expected_cols = [
        "vehicle", "stop_seq", "delivery_id", "location",
        "arrival", "start", "depart", "wait", "load_after",
        "window", "status"
    ]
    assert list(df.columns) == expected_cols
    assert len(df) > 0
    assert all(df["status"].isin(["pending", "completed"]))
    assert all(df["vehicle"].isin(list(s.env.vehicles.keys())))
    assert all(isinstance(seq, (int, float)) for seq in df["stop_seq"])


def test_unfulfilled_table_after_breakdown():
    if not HAS_PANDAS:
        return
    s = session()
    r = s.preview({"type": "vehicle_breakdown", "vehicle_id": "V1", "time": "09:10"})
    assert r["accepted"]
    s.apply(r["id"])
    df = unfulfilled_table(s.plan, s.env)
    expected_cols = ["delivery_id", "location", "weight", "window", "reason", "proven"]
    assert list(df.columns) == expected_cols
    assert len(df) > 0
    assert all(df["delivery_id"].str.startswith("D"))
    assert all(isinstance(reason, str) and len(reason) > 0 for reason in df["reason"])
    assert all(isinstance(p, (bool, int)) for p in df["proven"])


def test_comparison_table_after_incident():
    if not HAS_PANDAS:
        return
    s = session()
    r = s.preview({"type": "vehicle_breakdown", "vehicle_id": "V1", "time": "09:10"})
    assert r["accepted"]
    df = comparison_table(r["comparison"])
    expected_cols = [
        "delivery", "status", "vehicle_before", "vehicle_after",
        "eta_before", "eta_after", "reason"
    ]
    assert list(df.columns) == expected_cols
    assert len(df) == len(r["comparison"])
    assert set(df["status"]).issubset({"kept", "moved", "broken", "new"})
    assert all(isinstance(d, str) for d in df["delivery"])


def test_csv_export_string():
    if not HAS_PANDAS:
        return
    s = session()
    df = plan_table(s.plan, s.env)
    csv_str = export_csv(df)
    assert isinstance(csv_str, str)
    lines = csv_str.strip().splitlines()
    assert len(lines) == len(df) + 1
    assert lines[0] == "vehicle,stop_seq,delivery_id,location,arrival,start,depart,wait,load_after,window,status"


def test_excel_export_bytes():
    if not HAS_PANDAS:
        return
    s = session()
    dfs = {
        "Plan": plan_table(s.plan, s.env),
        "Unfulfilled": unfulfilled_table(s.plan, s.env),
    }
    try:
        data = export_excel(dfs)
        assert isinstance(data, bytes)
        assert len(data) > 0
    except Exception as e:
        if "openpyxl" in str(e).lower():
            pass
        else:
            raise


def test_server_export_endpoints():
    if not HAS_PANDAS:
        return
    # Test server endpoint logic using dummy handler simulation
    s = session()
    server.SESSION = s

    class DummyHeaders:
        def get(self, key, default=""):
            return default

    class DummyHandler(server.Handler):
        def __init__(self, path):
            self.path = path
            self.responses = []
            self.headers = DummyHeaders()

        def _send(self, code, obj, ctype="application/json", headers=None, session_id=None, set_cookie=False):
            self.responses.append({"code": code, "body": obj, "ctype": ctype, "headers": headers or {}})

    # 1. plan CSV
    h1 = DummyHandler("/api/export?format=csv&report=plan")
    h1.do_GET()
    assert h1.responses[0]["code"] == 200
    assert h1.responses[0]["ctype"] == "text/csv; charset=utf-8"
    assert "plan.csv" in h1.responses[0]["headers"].get("Content-Disposition", "")
    assert b"vehicle,stop_seq,delivery_id" in h1.responses[0]["body"]

    # 2. unfulfilled CSV
    h2 = DummyHandler("/api/export?format=csv&report=unfulfilled")
    h2.do_GET()
    assert h2.responses[0]["code"] == 200
    assert h2.responses[0]["ctype"] == "text/csv; charset=utf-8"
    assert "unfulfilled.csv" in h2.responses[0]["headers"].get("Content-Disposition", "")
    assert b"delivery_id,location,weight" in h2.responses[0]["body"]

    # 3. comparison CSV
    h3 = DummyHandler("/api/export?format=csv&report=comparison")
    h3.do_GET()
    assert h3.responses[0]["code"] == 200
    assert h3.responses[0]["ctype"] == "text/csv; charset=utf-8"
    assert "comparison.csv" in h3.responses[0]["headers"].get("Content-Disposition", "")
    assert b"delivery,status,vehicle_before" in h3.responses[0]["body"]

    # 4. excel export
    try:
        h4 = DummyHandler("/api/export?format=excel")
        h4.do_GET()
        assert h4.responses[0]["code"] == 200
        assert "spreadsheetml" in h4.responses[0]["ctype"]
        assert "reroute_export.xlsx" in h4.responses[0]["headers"].get("Content-Disposition", "")
    except Exception as e:
        if "openpyxl" in str(e).lower():
            pass
        else:
            raise
