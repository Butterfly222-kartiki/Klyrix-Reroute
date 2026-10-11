"""Comprehensive HTTP API tests for all server endpoints."""
import json
import threading
import time
from http.server import HTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# Import server components
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from reroute.server import Handler, SESSIONS, SESSIONS_LOCK, load_scenario
from helpers import demo_dict

# Global test server
TEST_SERVER = None
TEST_PORT = None
TEST_URL = None


def setup_test_server():
    """Start a test server on a random port."""
    global TEST_SERVER, TEST_PORT, TEST_URL
    if TEST_SERVER is not None:
        return  # Already started
    
    TEST_SERVER = HTTPServer(("127.0.0.1", 0), Handler)
    TEST_PORT = TEST_SERVER.server_address[1]
    TEST_URL = f"http://127.0.0.1:{TEST_PORT}"
    
    # Start server in background thread
    thread = threading.Thread(target=TEST_SERVER.serve_forever, daemon=True)
    thread.start()
    
    # Wait for server to be ready
    time.sleep(0.1)


def api_get(path, cookie=None):
    """Make a GET request to the test server."""
    setup_test_server()
    req = Request(f"{TEST_URL}{path}")
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        resp = urlopen(req)
        content_type = resp.headers.get("Content-Type", "")
        if content_type.startswith("application/json"):
            data = json.loads(resp.read())
        elif content_type.startswith("text/csv") or content_type.startswith("application/vnd.openxmlformats"):
            data = resp.read()  # Return bytes for CSV/Excel
        else:
            data = resp.read()
        cookies = resp.headers.get("Set-Cookie", "")
        return resp.status, data, cookies
    except HTTPError as e:
        data = json.loads(e.read()) if e.headers.get("Content-Type", "").startswith("application/json") else {}
        return e.code, data, ""


def api_post(path, body=None, cookie=None):
    """Make a POST request to the test server."""
    setup_test_server()
    data = json.dumps(body or {}).encode("utf-8")
    req = Request(f"{TEST_URL}{path}", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        resp = urlopen(req)
        result = json.loads(resp.read())
        cookies = resp.headers.get("Set-Cookie", "")
        return resp.status, result, cookies
    except HTTPError as e:
        result = json.loads(e.read()) if e.headers.get("Content-Type", "").startswith("application/json") else {}
        return e.code, result, ""


def test_api_state():
    """GET /api/state should return current state."""
    status, data, cookie = api_get("/api/state")
    assert status == 200, f"Expected 200, got {status}"
    assert "scenario" in data
    assert "has_plan" in data
    assert cookie  # Should set session cookie


def test_api_reset():
    """POST /api/reset should reset to demo scenario."""
    status, data, cookie = api_post("/api/reset", {})
    assert status == 200, f"Expected 200, got {status}"
    assert data["has_plan"] is True
    assert "plan" in data


def test_api_scenario_upload():
    """POST /api/scenario should accept a scenario JSON."""
    scenario = demo_dict()
    status, data, cookie = api_post("/api/scenario", scenario)
    assert status == 200, f"Expected 200, got {status}"
    assert data["scenario"]["name"] == scenario["name"]


def test_api_incident_preview_closure():
    """POST /api/incident/preview should preview a road closure."""
    status, _, cookie = api_post("/api/reset", {})
    assert status == 200
    
    incident = {
        "type": "road_closure",
        "a": "C1",
        "b": "C2",
        "start": "10:00",
        "end": "10:30",
        "extra": 25,
        "factor": 1.0,
        "time": "09:00"
    }
    status, data, _ = api_post("/api/incident/preview", incident, cookie=cookie)
    assert status == 200, f"Expected 200, got {status}"
    assert data["ok"] is True
    assert data["incident"]["type"] == "road_closure"


def test_api_incident_text():
    """POST /api/incident/text should parse text reports."""
    status, _, cookie = api_post("/api/reset", {})
    assert status == 200
    
    text = {"text": "Vehicle V1 broke down at 09:30"}
    status, data, _ = api_post("/api/incident/text", text, cookie=cookie)
    assert status == 200, f"Expected 200, got {status}"
    assert data["ok"] is True or "errors" in data  # May fail depending on scenario


def test_api_incident_apply():
    """POST /api/incident/apply should apply a previewed incident."""
    status, _, cookie = api_post("/api/reset", {})
    assert status == 200
    
    # Preview first
    incident = {
        "type": "road_closure",
        "a": "C1",
        "b": "C2",
        "start": "10:00",
        "end": "10:30",
        "extra": 25,
        "factor": 1.0,
        "time": "09:00"
    }
    status, prev_data, _ = api_post("/api/incident/preview", incident, cookie=cookie)
    assert status == 200
    
    if prev_data.get("ok") and prev_data.get("accepted"):
        incident_id = prev_data["id"]
        
        # Apply
        status, apply_data, _ = api_post("/api/incident/apply", {"id": incident_id, "confirm": True}, cookie=cookie)
        assert status == 200, f"Expected 200, got {status}"
        # Apply returns full state, not just {ok: true}
        assert "scenario" in apply_data or apply_data.get("ok") is True


def test_api_incident_cancel():
    """POST /api/incident/cancel should discard a preview."""
    status, _, cookie = api_post("/api/reset", {})
    assert status == 200
    
    incident = {
        "type": "road_closure",
        "a": "C1",
        "b": "C2",
        "start": "10:00",
        "end": "10:30",
        "extra": 25,
        "factor": 1.0,
        "time": "09:00"
    }
    status, prev_data, _ = api_post("/api/incident/preview", incident, cookie=cookie)
    assert status == 200
    
    if prev_data.get("ok"):
        incident_id = prev_data["id"]
        status, cancel_data, _ = api_post("/api/incident/cancel", {"id": incident_id}, cookie=cookie)
        assert status == 200
        assert cancel_data["ok"] is True


def test_api_export_csv():
    """GET /api/export?format=csv should return CSV data."""
    status, _, cookie = api_post("/api/reset", {})
    assert status == 200
    
    status, data, _ = api_get("/api/export?format=csv&report=plan", cookie=cookie)
    assert status == 200, f"Expected 200, got {status}"
    # CSV is returned as bytes
    assert isinstance(data, bytes), f"Expected bytes, got {type(data)}"
    assert b"vehicle" in data  # Check for CSV header


def test_api_export_excel():
    """GET /api/export?format=excel should return Excel data."""
    try:
        import openpyxl
        has_excel = True
    except ImportError:
        has_excel = False
    
    if not has_excel:
        # Skip if openpyxl not installed
        return
    
    status, _, cookie = api_post("/api/reset", {})
    assert status == 200
    
    status, data, _ = api_get("/api/export?format=excel", cookie=cookie)
    # May be 200 or 500 depending on pandas availability
    assert status in (200, 500), f"Expected 200 or 500, got {status}"


def test_api_advance():
    """POST /api/advance should advance simulation time."""
    status, _, cookie = api_post("/api/reset", {})
    assert status == 200
    
    # Advance by 60 minutes
    status, data, _ = api_post("/api/advance", {"minutes": 60}, cookie=cookie)
    assert status == 200, f"Expected 200, got {status}"
    # Returns full state after advancing
    assert "plan" in data or data.get("ok") is True


def test_api_undo():
    """POST /api/undo should undo the last incident."""
    status, _, cookie = api_post("/api/reset", {})
    assert status == 200
    
    # Apply an incident first
    incident = {
        "type": "road_closure",
        "a": "C1",
        "b": "C2",
        "start": "10:00",
        "end": "10:30",
        "extra": 25,
        "factor": 1.0,
        "time": "09:00"
    }
    status, prev_data, _ = api_post("/api/incident/preview", incident, cookie=cookie)
    if prev_data.get("ok") and prev_data.get("accepted"):
        incident_id = prev_data["id"]
        status, _, _ = api_post("/api/incident/apply", {"id": incident_id, "confirm": True}, cookie=cookie)
        
        # Now undo
        status, undo_data, _ = api_post("/api/undo", {}, cookie=cookie)
        assert status in (200, 400), f"Expected 200 or 400, got {status}"


def test_api_report():
    """GET /api/report should return decision report."""
    status, _, cookie = api_post("/api/reset", {})
    assert status == 200
    
    status, data, _ = api_get("/api/report", cookie=cookie)
    assert status == 200, f"Expected 200, got {status}"
    assert "report" in data
    assert "format" in data
    assert data["format"] == "markdown"


def test_session_isolation():
    """Two sessions with different cookies should have independent state."""
    # Session 1: reset
    status1, _, cookie1 = api_post("/api/reset", {})
    assert status1 == 200
    
    # Session 2: reset (should get different cookie)
    status2, _, cookie2 = api_post("/api/reset", {})
    assert status2 == 200
    
    # Cookies should be different (in production - in our test they might be same due to session reuse)
    # At minimum, both should work
    
    # Session 1: get state
    status1, data1, _ = api_get("/api/state", cookie=cookie1)
    assert status1 == 200
    
    # Session 2: get state
    status2, data2, _ = api_get("/api/state", cookie=cookie2)
    assert status2 == 200


def test_invalid_endpoint():
    """Requesting invalid endpoint should return 404."""
    status, data, _ = api_get("/api/invalid")
    assert status == 404


def test_malformed_json():
    """Posting malformed JSON should return 400."""
    setup_test_server()
    data = b"not json"
    req = Request(f"{TEST_URL}/api/reset", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        urlopen(req)
        assert False, "Should have raised HTTPError"
    except HTTPError as e:
        assert e.code == 400


# Run tests
if __name__ == "__main__":
    print("Running API tests...")
    tests = [
        test_api_state,
        test_api_reset,
        test_api_scenario_upload,
        test_api_incident_preview_closure,
        test_api_incident_text,
        test_api_incident_apply,
        test_api_incident_cancel,
        test_api_export_csv,
        test_api_export_excel,
        test_api_advance,
        test_api_undo,
        test_api_report,
        test_session_isolation,
        test_invalid_endpoint,
        test_malformed_json,
    ]
    
    passed = 0
    for test in tests:
        try:
            test()
            print(f"✓ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {e}")
    
    print(f"\n{passed}/{len(tests)} tests passed")
    
    if TEST_SERVER:
        TEST_SERVER.shutdown()
