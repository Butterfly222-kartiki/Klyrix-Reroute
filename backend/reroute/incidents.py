"""Incident validation (structured) and deterministic text interpretation (with confirmation)."""
from __future__ import annotations
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from .models import Delivery, Closure, ValidationError, to_minutes, fmt_time
from .schedule import Env

ROAD_CLOSURE, BREAKDOWN, URGENT = "road_closure", "vehicle_breakdown", "urgent_order"


class IncidentError(ValueError):
    def __init__(self, errors):
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


@dataclass
class Incident:
    type: str
    time: float                      # simulation time at which the dispatcher learns of it
    data: dict
    source: str = "structured"       # structured | text
    raw_text: Optional[str] = None
    interpretation: str = ""
    assumptions: List[str] = field(default_factory=list)

    def describe(self) -> str:
        d = self.data
        if self.type == ROAD_CLOSURE:
            extra = f"+{d['extra']:g} min" if d["extra"] else f"x{d['factor']:g}"
            return (f"Road {d['a']}-{d['b']} slowed ({extra}) from {fmt_time(d['start'])} to {fmt_time(d['end'])}"
                    f"; reported at {fmt_time(self.time)}")
        if self.type == BREAKDOWN:
            return f"Vehicle {d['vehicle_id']} breaks down at {fmt_time(self.time)}"
        dl = d["delivery"]
        return (f"Urgent order {dl['id']} to {dl['location']} ({dl['weight']:g} units), window "
                f"{fmt_time(dl['tw_start'])}-{fmt_time(dl['tw_end'])}, received {fmt_time(self.time)}")

    def to_dict(self):
        out = asdict(self)
        out["description"] = self.describe()
        return out


def _canon(env: Env) -> Dict[str, str]:
    return {n.lower(): n for n in env.locations}


def validate_incident(raw: dict, env: Env, now: float, failed: Dict[str, dict], existing_ids=()) -> Incident:
    """Reject anything referencing unknown locations/vehicles instead of guessing."""
    errs: List[str] = []
    typ = raw.get("type")
    canon = _canon(env)
    try:
        t = to_minutes(raw["time"]) if raw.get("time") is not None else None
    except ValidationError as e:
        raise IncidentError(str(e))
    if typ == ROAD_CLOSURE:
        a, b = canon.get(str(raw.get("a", "")).lower()), canon.get(str(raw.get("b", "")).lower())
        for k, v in (("a", a), ("b", b)):
            if v is None:
                errs.append(f"Unknown location '{raw.get(k)}'")
        try:
            st, en = to_minutes(raw["start"]), to_minutes(raw["end"])
        except (KeyError, ValidationError) as e:
            raise IncidentError(errs + [f"Closure needs valid start/end times ({e})"])
        extra, factor = float(raw.get("extra", 0) or 0), float(raw.get("factor", 1) or 1)
        if a and a == b:
            errs.append("Closure endpoints must differ")
        if en <= st:
            errs.append("Closure end must be after start")
        if extra < 0 or factor < 1 or (extra == 0 and factor == 1):
            errs.append("Closure must increase travel time (extra > 0 or factor > 1)")
        if errs:
            raise IncidentError(errs)
        t = max(st, now) if t is None else t
        if t < now:
            raise IncidentError(f"Incident time {fmt_time(t)} is before current simulation time {fmt_time(now)}")
        eff_start = max(st, t)   # vehicles already past the closure start are assumed unaffected
        if en <= eff_start:
            raise IncidentError("Closure has already ended at the report time")
        data = dict(a=a, b=b, start=eff_start, end=en, extra=extra, factor=factor)
    elif typ == BREAKDOWN:
        vid = str(raw.get("vehicle_id", ""))
        if vid not in env.vehicles:
            errs.append(f"Unknown vehicle '{vid}'")
        elif vid in failed:
            errs.append(f"Vehicle {vid} has already failed")
        if t is None:
            errs.append("Breakdown needs a time")
        if errs:
            raise IncidentError(errs)
        if t < now:
            raise IncidentError(f"Incident time {fmt_time(t)} is before current simulation time {fmt_time(now)}")
        data = dict(vehicle_id=vid)
    elif typ == URGENT:
        dl = dict(raw.get("delivery") or {})
        loc = canon.get(str(dl.get("location", "")).lower())
        if loc is None:
            errs.append(f"Unknown location '{dl.get('location')}'")
        if t is None:
            errs.append("Urgent order needs a report time")
        if errs:
            raise IncidentError(errs)
        if t < now:
            raise IncidentError(f"Incident time {fmt_time(t)} is before current simulation time {fmt_time(now)}")
        used = set(existing_ids) | set(env.deliveries)
        did = str(dl.get("id") or "")
        if not did:
            k = 1
            while f"U{k}" in used:
                k += 1
            did = f"U{k}"
        if did in used:
            raise IncidentError(f"Delivery id '{did}' already exists")
        try:
            d = Delivery.from_dict({**dl, "id": did, "location": loc, "priority": 1, "release_time": t,
                                    "tw_start": dl.get("tw_start", t)})
        except (KeyError, ValidationError) as e:
            raise IncidentError(f"Invalid urgent order: {e}")
        if d.weight <= 0:
            raise IncidentError("Urgent order weight must be > 0")
        data = dict(delivery=asdict(d))
    else:
        raise IncidentError(f"Unknown incident type '{typ}'")
    return Incident(typ, t, data, raw.get("source", "structured"))


# ---------------------------------------------------------------- text interpretation
_T = r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)"
_TS = r"(\d{1,2}:\d{2}\s*(?:am|pm)?|\d{1,2}\s*(?:am|pm))"     # strict: colon or am/pm
_N = r"([\w\-\.]+)"
_RANGE = (r"(?:from|between)\s+" + _T + r"\s*(?:to|until|till|and|-)\s*" + _T +
          r"|" + _T + r"\s*(?:to|until|till|-)\s*" + _T)  # also "10:00 to 10:30" without from/between

# Vehicle name aliases: "Truck 2" -> "V2", "Van 1" -> "V1", etc.
def _resolve_vehicle(text: str, env: Env) -> Optional[str]:
    """Try to match a vehicle name or alias."""
    low = text.strip().lower()
    # Direct match
    v = next((v for v in env.vehicles if v.lower() == low), None)
    if v:
        return v
    # "Truck 2" / "Van 1" / "Vehicle 3" -> V2 / V1 / V3
    m = re.match(r"(?:truck|van|vehicle|bike)\s*(\d+)", low)
    if m:
        candidate = f"V{m.group(1)}"
        if candidate in env.vehicles:
            return candidate
    return None


def _parse_range(text: str):
    """Extract a time range from text, supporting various formats."""
    m = re.search(_RANGE, text.lower())
    if m:
        # Groups 1,2 from first alt or 3,4 from second alt
        return (m.group(1) or m.group(3), m.group(2) or m.group(4))
    return None


def _parse_single(text: str, env: Env, now: float, failed: Dict[str, dict],
                   existing_ids, canon: dict) -> dict:
    """Parse a single incident from text. Returns a result dict."""
    s = " ".join(text.strip().split())
    low = s.lower()
    res = {"ok": False, "text": text, "incident": None, "interpretation": "", "assumptions": [], "errors": []}
    if not s:
        res["errors"].append("Empty report")
        return res
    raw: Optional[dict] = None
    try:
        # --- Road closure patterns (widened) ---
        # Pattern 1: "road between X and Y closed ..." (original)
        # Pattern 2: "X to Y closed ..." or "X-Y closed ..."
        # Pattern 3: "closed between 10 and 10:30" style (time range after "closed")
        m = re.search(r"(?:road|route|link|street)\s+(?:between|from)\s+" + _N + r"\s+(?:and|to)\s+" + _N +
                      r"\b.*?(?:closed|closure|blocked|congested|slow|delayed)", low)
        if not m:
            # Try reversed: "closed|blocked ... road between X and Y"
            m = re.search(r"(?:closed|closure|blocked|congested|slow|delayed)\b.*?"
                          r"(?:road|route|link|street)\s+(?:between|from)\s+" + _N + r"\s+(?:and|to)\s+" + _N, low)
        if not m:
            # Try: "X to Y is closed/blocked" without road/route prefix
            m = re.search(_N + r"\s+(?:to|-)\s+" + _N +
                          r"\s+(?:is\s+)?(?:closed|blocked|congested|slow|delayed)", low)
        if m:
            rng = _parse_range(low[m.end():]) or _parse_range(low[:m.start()]) or _parse_range(low)
            if not rng:
                res["errors"].append("Closure period missing (expected 'from HH:MM to HH:MM' or 'between HH:MM and HH:MM')")
                return res
            ex = re.search(r"(?:adding|add|delay(?:ed)?(?: of| by)?|\+)\s*(\d+)\s*(?:min|minutes)", low)
            fac = re.search(r"(?:x|times|slower by)\s*(\d+(?:\.\d+)?)", low)
            unknown = [g for g in m.groups() if g not in canon]
            if unknown:
                res["errors"].append("Unknown location(s): " + ", ".join(unknown) + " - report rejected, nothing guessed")
                return res
            raw = {"type": ROAD_CLOSURE, "a": m.group(1), "b": m.group(2),
                   "start": rng[0], "end": rng[1]}
            if ex:
                raw["extra"] = float(ex.group(1))
            elif fac:
                raw["factor"] = float(fac.group(1))
            else:
                raw["extra"] = 600.0
                res["assumptions"].append("No delay given: treated as a full closure (+600 min while active).")
            res["assumptions"].append("Reported at the closure start (or current time if later).")
        else:
            # --- Vehicle breakdown patterns (widened) ---
            # Pattern 1: "(vehicle|truck|van|bike) <id>" where <id> could be "V1" or "2"
            m = re.search(r"((?:vehicle|truck|van|bike)\s+" + _N + r")" +
                          r"\s+(?:has\s+|just\s+)?(?:broke down|broken down|failed|breakdown|is down|stalled|stopped)", low)
            if m:
                # m.group(1) is the full vehicle phrase, m.group(2) is the _N capture
                # Try resolving the full phrase first ("truck 2"), then fall back to the ID part
                vehicle_text = m.group(1).strip()
                vid = _resolve_vehicle(vehicle_text, env)
                if vid is None:
                    # Fall back to just the ID part (e.g., "V1" from "vehicle V1")
                    vid = _resolve_vehicle(m.group(2), env)
            else:
                # Try: "V1 broke down" or "V2 has broken down"
                m = re.search(_N + r"\s+(?:has\s+|just\s+)?(?:broke down|broken down|failed|is down|stalled)", low)
                if m:
                    vid = _resolve_vehicle(m.group(1), env)
                else:
                    vid = None
            if m:
                at = re.search(r"\bat\s+" + _TS, low)
                if not at:
                    res["errors"].append("Breakdown time missing (expected 'at HH:MM')")
                    return res
                if vid is None:
                    # Figure out what we tried to resolve for error message
                    match_text = m.group(1) if len(m.groups()) >= 1 else ""
                    res["errors"].append(f"Unknown vehicle '{match_text}' - report rejected")
                    return res
                raw = {"type": BREAKDOWN, "vehicle_id": vid, "time": at.group(1)}
            else:
                # --- Urgent order patterns (widened) ---
                m = re.search(r"urgent\s+(?:order|delivery|parcel)\s+(?:for|to|at)\s+" + _N, low)
                if not m:
                    # Try "new order for/to X" or "rush delivery to X"
                    m = re.search(r"(?:new|rush|priority)\s+(?:order|delivery|parcel)\s+(?:for|to|at)\s+" + _N, low)
                if not m:
                    res["errors"].append("Could not interpret report. Supported: road closure, vehicle breakdown, urgent order.")
                    return res
                if m.group(1) not in canon:
                    res["errors"].append(f"Unknown location '{m.group(1)}' - report rejected, nothing guessed")
                    return res
                wt = re.search(r"(\d+(?:\.\d+)?)\s*(?:kg|units?|packages?|boxes)", low)
                rng = _parse_range(low)
                rec = re.search(r"(?:received|reported|placed|came in|arrived)\s+(?:at\s+)?" + _TS, low)
                if not wt:
                    res["errors"].append("Weight missing (e.g. '15 kg')")
                if not rng:
                    res["errors"].append("Delivery window missing (e.g. 'between 10:30 and 11:30')")
                if res["errors"]:
                    return res
                raw = {"type": URGENT, "time": rec.group(1) if rec else now,
                       "delivery": {"location": m.group(1), "weight": float(wt.group(1)),
                                    "tw_start": rng[0], "tw_end": rng[1]}}
                if not rec:
                    res["assumptions"].append(f"No report time: assumed current time {fmt_time(now)}.")
        raw["source"] = "text"
        inc = validate_incident(raw, env, now, failed, existing_ids)
    except IncidentError as e:
        res["errors"].extend(e.errors)
        return res
    inc.source, inc.raw_text, inc.assumptions = "text", text, res["assumptions"]
    inc.interpretation = inc.describe()
    res.update(ok=True, incident=inc.to_dict(), interpretation=inc.interpretation)
    return res


def parse_text(text: str, env: Env, now: float, failed: Dict[str, dict], existing_ids=()) -> dict:
    """Deterministic interpreter. NEVER applies anything: returns a proposal for dispatcher confirmation.
    Supports multiple incidents separated by semicolons or 'and then'.
    If REROUTE_LLM=1 is set, falls back to LLM interpretation (through the same validation path).
    
    Returns:
    - Single incident: {"ok": bool, "incident": {...}, ...}
    - Multiple incidents: {"ok": bool, "incidents": [{...}, {...}], ...}
    """
    import os
    from .llm_config import llm_enabled
    # Try deterministic parser first (always)
    # Support multiple incidents: split on ';' or 'and then'
    parts = re.split(r'\s*;\s*|\s+and\s+then\s+', text.strip())
    parts = [p.strip() for p in parts if p.strip()]
    
    if len(parts) <= 1:
        result = _parse_single(text, env, now, failed, existing_ids, _canon(env))
        if result["ok"] or not llm_enabled():
            return result
        # LLM fallback
        return _llm_interpret(text, env, now, failed, existing_ids) or result
    
    # Multiple incidents: parse each, return as a list
    canon = _canon(env)
    results = []
    errors = []
    for part in parts:
        result = _parse_single(part, env, now, failed, existing_ids, canon)
        if result["ok"]:
            results.append(result)
        else:
            errors.extend(result["errors"])
    
    if not results:
        # All failed
        return {"ok": False, "errors": errors, "text": text}
    
    # Return list of incidents
    return {
        "ok": True,
        "text": text,
        "incidents": [r["incident"] for r in results],
        "interpretations": [r["interpretation"] for r in results],
        "assumptions": [a for r in results for a in r.get("assumptions", [])],
        "errors": errors if errors else []
    }


def _llm_interpret(text: str, env: Env, now: float, failed: Dict[str, dict], existing_ids) -> Optional[dict]:
    """Optional LLM-based interpretation. Only called if REROUTE_LLM=1 is set.
    The LLM output goes through the SAME validate_incident + confirmation path.
    Returns None if LLM is unavailable or fails."""
    import os
    from .llm_config import llm_enabled, llm_key, llm_chat_url
    if not llm_enabled():
        return None
    try:
        import json
        import urllib.request
        
        api_key = llm_key()
        if not api_key:
            return None
        
        # Build a prompt describing the expected JSON structure
        locations = list(env.locations.keys())
        vehicles = list(env.vehicles.keys())
        prompt = (
            f"Parse this dispatcher report into a structured incident JSON.\n"
            f"Available locations: {locations}\n"
            f"Available vehicles: {vehicles}\n"
            f"Current time: {fmt_time(now)}\n"
            f"Report: \"{text}\"\n\n"
            f"Respond with ONLY valid JSON in one of these formats:\n"
            f'  {{"type": "road_closure", "a": "LOC", "b": "LOC", "start": "HH:MM", "end": "HH:MM", "extra": N}}\n'
            f'  {{"type": "vehicle_breakdown", "vehicle_id": "VX", "time": "HH:MM"}}\n'
            f'  {{"type": "urgent_order", "time": "HH:MM", "delivery": {{"location": "LOC", "weight": N, "tw_start": "HH:MM", "tw_end": "HH:MM"}}}}\n'
        )
        
        # Build the API request
        request_data = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "You are a parser that converts dispatcher reports to structured JSON."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0
        }
        
        req = urllib.request.Request(
            llm_chat_url(),
            data=json.dumps(request_data).encode('utf-8'),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
        )
        
        # Make the request with 10 second timeout
        with urllib.request.urlopen(req, timeout=10) as response:
            response_data = json.loads(response.read().decode('utf-8'))
            
        # Extract the response content
        content = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            return None
        
        # Try to parse the JSON from the response
        # The LLM might wrap it in markdown code blocks, so strip those
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        incident_data = json.loads(content)
        
        # Validate the incident through the same path
        inc = validate_incident(incident_data, env, now, failed, existing_ids)
        inc.source = "text"
        inc.raw_text = text
        inc.interpretation = inc.describe()
        inc.assumptions = ["Interpreted by LLM (REROUTE_LLM=1)"]
        
        return {"ok": True, "incident": inc.to_dict(), "interpretation": inc.interpretation,
                "assumptions": inc.assumptions, "errors": []}
    except Exception:
        # Any error: return None to fall back to deterministic parser result
        return None

