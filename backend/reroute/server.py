"""Zero-dependency HTTP server: JSON API + static dispatcher dashboard.  python -m reroute.server"""
from __future__ import annotations
import json, mimetypes, os, sys, traceback, secrets, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

try:
    from .export import (
        plan_table,
        comparison_table,
        unfulfilled_table,
        export_csv,
        export_excel,
        HAS_PANDAS,
    )
except ImportError:
    HAS_PANDAS = False

from .api_models import (
    IncidentInput,
    TextIncidentInput,
    ApplyInput,
    ScenarioInput,
    SaveInput,
    LoadInput,
    validate_api_input,
)
from .engine import PlanRejected, Session
from .models import Scenario, ValidationError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
DEMO = os.path.join(ROOT, "data", "demo_scenario.json")
from .llm_config import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"), os.path.join(os.path.dirname(ROOT), ".env"))
SCEN_DIR = os.path.join(ROOT, "data", "scenarios")      # saved scenarios (JSON storage)

# Session management
SESSIONS: dict[str, Session] = {}
SESSIONS_LOCK = threading.Lock()
SESSION: Session = None  # Kept for backward compatibility


def load_scenario(d: dict) -> Session:
    s = Session(Scenario.from_dict(d))
    s.plan_initial()
    return s


def get_session(handler: BaseHTTPRequestHandler) -> tuple[str, Session]:
    """Get or create session from cookie. Returns (session_id, session)."""
    # Parse cookie header
    cookie_header = handler.headers.get("Cookie", "")
    session_id = None
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith("reroute_session="):
            session_id = part.split("=", 1)[1]
            break
    
    with SESSIONS_LOCK:
        # Check if session exists
        if session_id and session_id in SESSIONS:
            return session_id, SESSIONS[session_id]
        
        # Create new session
        session_id = secrets.token_hex(16)
        SESSIONS[session_id] = load_scenario(json.load(open(DEMO)))
        return session_id, SESSIONS[session_id]


def _field(model, body: dict, key: str, default=None):
    """Read a validated field; works with a pydantic model or the raw dict used when pydantic is absent."""
    if model is not None and not isinstance(model, dict):
        return getattr(model, key, default)
    return body.get(key, default)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj, ctype="application/json", headers: dict | None = None, session_id: str | None = None, set_cookie: bool = False):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        origin = self.headers.get("Origin")
        if origin:                                   # allow the PWA/frontend on another origin (cookies included)
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Vary", "Origin")
        if set_cookie and session_id:
            self.send_header("Set-Cookie", f"reroute_session={session_id}; HttpOnly; SameSite=Lax; Path=/")
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        origin = self.headers.get("Origin") or "*"
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        # Get or create session
        session_id, session = get_session(self)
        is_new_session = session_id not in [sid for sid in SESSIONS if sid != session_id]  # Check if we just created it
        
        if path == "/api/state":
            return self._send(200, session.state(), session_id=session_id, set_cookie=is_new_session)
        if path == "/api/scenarios":
            os.makedirs(SCEN_DIR, exist_ok=True)
            return self._send(200, sorted(f[:-5] for f in os.listdir(SCEN_DIR) if f.endswith(".json")), 
                            session_id=session_id, set_cookie=is_new_session)
        if path == "/api/export":
            if not HAS_PANDAS:
                return self._send(500, {"error": "pandas is required for export functionality"}, 
                                session_id=session_id, set_cookie=is_new_session)
            if session is None or session.plan is None:
                return self._send(400, {"error": "No active plan to export"}, 
                                session_id=session_id, set_cookie=is_new_session)
            qs = parse_qs(parsed.query)
            fmt = qs.get("format", ["csv"])[0].lower()
            report = qs.get("report", ["plan"])[0].lower()

            if fmt in ("excel", "xlsx"):
                dfs = {
                    "Plan": plan_table(session.plan, session.env),
                    "Comparison": comparison_table(session.last_comparison.get("rows", []) if session.last_comparison else []),
                    "Unfulfilled": unfulfilled_table(session.plan, session.env),
                }
                data = export_excel(dfs)
                return self._send(
                    200,
                    data,
                    ctype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="reroute_export.xlsx"'},
                    session_id=session_id,
                    set_cookie=is_new_session
                )
            elif fmt == "csv":
                if report == "plan":
                    df = plan_table(session.plan, session.env)
                    fname = "plan.csv"
                elif report == "comparison":
                    rows = session.last_comparison.get("rows", []) if session.last_comparison else []
                    df = comparison_table(rows)
                    fname = "comparison.csv"
                elif report == "unfulfilled":
                    df = unfulfilled_table(session.plan, session.env)
                    fname = "unfulfilled.csv"
                else:
                    return self._send(400, {"error": f"Unknown report type: {report}"}, 
                                    session_id=session_id, set_cookie=is_new_session)

                csv_text = export_csv(df)
                return self._send(
                    200,
                    csv_text.encode("utf-8"),
                    ctype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'},
                    session_id=session_id,
                    set_cookie=is_new_session
                )
            else:
                return self._send(400, {"error": f"Unsupported format: {fmt}"}, 
                                session_id=session_id, set_cookie=is_new_session)
        if path == "/api/report":
            # Generate decision report
            if session is None or session.plan is None:
                report_text = "# ReRoute Decision Report\n\nNo active plan yet.\n"
            else:
                report_text = session.report()
            return self._send(200, {"report": report_text, "format": "markdown"}, 
                            session_id=session_id, set_cookie=is_new_session)
        f = os.path.join(WEB, "index.html" if path in ("/", "") else path.lstrip("/"))
        if os.path.commonpath([WEB, os.path.abspath(f)]) == WEB and os.path.isfile(f):
            return self._send(200, open(f, "rb").read(), mimetypes.guess_type(f)[0] or "application/octet-stream")
        self._send(404, {"error": "not found"})

    def do_POST(self):
        global SESSION
        path = urlparse(self.path).path
        
        # Get or create session
        session_id, session = get_session(self)
        # Check if this is a new session (not in SESSIONS before this call, except for the one we just added)
        with SESSIONS_LOCK:
            is_new_session = len([sid for sid in SESSIONS if sid != session_id]) == 0
        
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if path == "/api/reset":
                with SESSIONS_LOCK:
                    SESSIONS[session_id] = load_scenario(json.load(open(DEMO)))
                    session = SESSIONS[session_id]
                return self._send(200, session.state(), session_id=session_id, set_cookie=True)
            if path == "/api/scenario":                       # upload a scenario JSON
                model, errs = validate_api_input(ScenarioInput, body)
                if errs:
                    return self._send(400, {"errors": errs}, session_id=session_id, set_cookie=is_new_session)
                with SESSIONS_LOCK:
                    SESSIONS[session_id] = load_scenario(body)
                    session = SESSIONS[session_id]
                return self._send(200, session.state(), session_id=session_id, set_cookie=True)
            if path == "/api/scenario/save":
                model, errs = validate_api_input(SaveInput, body)
                if errs:
                    return self._send(400, {"errors": errs}, session_id=session_id, set_cookie=is_new_session)
                os.makedirs(SCEN_DIR, exist_ok=True)
                raw_name = _field(model, body, "name", "scenario")
                name = "".join(c for c in raw_name if c.isalnum() or c in "-_") or "scenario"
                json.dump(session.scenario.to_dict(), open(os.path.join(SCEN_DIR, name + ".json"), "w"), indent=1)
                return self._send(200, {"saved": name}, session_id=session_id, set_cookie=is_new_session)
            if path == "/api/scenario/load":
                model, errs = validate_api_input(LoadInput, body)
                if errs:
                    return self._send(400, {"errors": errs}, session_id=session_id, set_cookie=is_new_session)
                raw_name = _field(model, body, "name", "")
                name = "".join(c for c in raw_name if c.isalnum() or c in "-_")
                with SESSIONS_LOCK:
                    SESSIONS[session_id] = load_scenario(json.load(open(os.path.join(SCEN_DIR, name + ".json"))))
                    session = SESSIONS[session_id]
                return self._send(200, session.state(), session_id=session_id, set_cookie=True)
            if path == "/api/incident/preview":
                model, errs = validate_api_input(IncidentInput, body)
                if errs:
                    return self._send(400, {"errors": errs}, session_id=session_id, set_cookie=is_new_session)
                return self._send(200, session.preview(raw=body), session_id=session_id, set_cookie=is_new_session)
            if path == "/api/incident/text":
                model, errs = validate_api_input(TextIncidentInput, body)
                if errs:
                    return self._send(400, {"errors": errs}, session_id=session_id, set_cookie=is_new_session)
                text_val = _field(model, body, "text", "")
                return self._send(200, session.preview(text=text_val), session_id=session_id, set_cookie=is_new_session)
            if path == "/api/incident/apply":
                model, errs = validate_api_input(ApplyInput, body)
                if errs:
                    return self._send(400, {"errors": errs}, session_id=session_id, set_cookie=is_new_session)
                apply_id = _field(model, body, "id")
                confirm_val = _field(model, body, "confirm", False)
                session.apply(apply_id, bool(confirm_val))
                return self._send(200, session.state(), session_id=session_id, set_cookie=is_new_session)
            if path == "/api/incident/cancel":
                session.cancel(body.get("id", ""))
                return self._send(200, {"ok": True}, session_id=session_id, set_cookie=is_new_session)
            if path == "/api/advance":
                # Advance simulation time
                time_str = body.get("time")
                minutes = body.get("minutes")
                if time_str:
                    # Parse HH:MM format
                    from .models import parse_time
                    new_time = parse_time(time_str)
                    minutes = new_time - session.plan.now
                elif minutes is None:
                    return self._send(400, {"error": "Must provide 'time' (HH:MM) or 'minutes' (number)"}, session_id=session_id, set_cookie=is_new_session)
                session.advance_time(float(minutes))
                return self._send(200, session.state(), session_id=session_id, set_cookie=is_new_session)
            if path == "/api/undo":
                session.undo()
                return self._send(200, session.state(), session_id=session_id, set_cookie=is_new_session)
            if path == "/api/ai/messages":
                # Generate customer messages
                from .ai_module import generate_customer_messages
                comp = body.get("comparison", {})
                rows = comp.get("rows", [])
                messages = generate_customer_messages(rows, session.env)
                return self._send(200, {"messages": messages}, session_id=session_id, set_cookie=is_new_session)
            if path == "/api/ai/why":
                # Answer "why?" question
                from .ai_module import answer_why_question
                question = body.get("question", "")
                result = answer_why_question(question, session.state(), 
                                            session.last_comparison or {}, session.events)
                return self._send(200, result, session_id=session_id, set_cookie=is_new_session)
            if path == "/api/ai/alerts":
                # Get predictive alerts
                from .ai_module import check_window_violations
                threshold = body.get("threshold_minutes", 10)
                alerts = check_window_violations(session.state(), session.env, threshold)
                return self._send(200, {"alerts": alerts}, session_id=session_id, set_cookie=is_new_session)
            self._send(404, {"error": "not found"}, session_id=session_id, set_cookie=is_new_session)
        except (PlanRejected, ValidationError, KeyError, FileNotFoundError, json.JSONDecodeError) as e:
            self._send(400, {"error": f"{type(e).__name__}: {e}"}, session_id=session_id, set_cookie=is_new_session)
        except Exception as e:                                  # never leak a stack trace to the UI
            traceback.print_exc()
            self._send(500, {"error": f"Internal error: {e}"}, session_id=session_id, set_cookie=is_new_session)


def main(port: int = 8000, host: str = "127.0.0.1"):
    global SESSION
    # Initialize a default session for backward compatibility
    SESSION = load_scenario(json.load(open(DEMO)))
    # Also add it to SESSIONS with a default ID
    with SESSIONS_LOCK:
        SESSIONS["default"] = SESSION
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"ReRoute dashboard: http://{host}:{port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8000)), os.environ.get("REROUTE_HOST", "127.0.0.1"))
