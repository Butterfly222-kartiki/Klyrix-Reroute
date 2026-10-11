"""Pandas tables + CSV/Excel export for plans, comparisons, and unfulfilled deliveries."""
from __future__ import annotations
import io
from typing import Any, Dict, List, Optional

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    pd = None
    HAS_PANDAS = False

from .models import fmt_time
from .plan import Plan
from .schedule import Env


def plan_table(plan: Plan, env: Env) -> Any:
    """DataFrame with columns: vehicle, stop_seq, delivery_id, location, arrival, start, depart, wait, load_after, window, status."""
    if not HAS_PANDAS:
        raise ImportError("pandas is required for export functions. Install with: pip install pandas")
    columns = [
        "vehicle", "stop_seq", "delivery_id", "location",
        "arrival", "start", "depart", "wait", "load_after",
        "window", "status"
    ]
    rows = []
    evs = plan.evaluate(env)
    for vid in sorted(env.vehicles.keys()):
        seq = 0
        # Completed history stops (frozen)
        for r in plan.history.get(vid, []):
            did = r.get("stop_id", "")
            tw_s, tw_e = r.get("tw_start"), r.get("tw_end")
            if tw_s is None and did in env.deliveries:
                tw_s, tw_e = env.deliveries[did].tw_start, env.deliveries[did].tw_end
            win = f"{fmt_time(tw_s)}-{fmt_time(tw_e)}" if tw_s is not None and tw_e is not None else ""
            rows.append({
                "vehicle": vid,
                "stop_seq": seq,
                "delivery_id": did,
                "location": r.get("location", ""),
                "arrival": round(r["arrival"], 1) if isinstance(r.get("arrival"), (int, float)) else r.get("arrival"),
                "start": round(r["start"], 1) if isinstance(r.get("start"), (int, float)) else r.get("start"),
                "depart": round(r["depart"], 1) if isinstance(r.get("depart"), (int, float)) else r.get("depart"),
                "wait": round(r["wait"], 1) if isinstance(r.get("wait"), (int, float)) else r.get("wait"),
                "load_after": round(r["load_after"], 1) if isinstance(r.get("load_after"), (int, float)) else r.get("load_after"),
                "window": win,
                "status": "completed",
            })
            seq += 1

        # Pending stops
        ev = evs.get(vid)
        if ev and ev.rows:
            for r in ev.rows:
                did = r.get("stop_id", "")
                tw_s, tw_e = r.get("tw_start"), r.get("tw_end")
                if tw_s is None and did in env.deliveries:
                    tw_s, tw_e = env.deliveries[did].tw_start, env.deliveries[did].tw_end
                win = f"{fmt_time(tw_s)}-{fmt_time(tw_e)}" if tw_s is not None and tw_e is not None else ""
                rows.append({
                    "vehicle": vid,
                    "stop_seq": seq,
                    "delivery_id": did,
                    "location": r.get("location", ""),
                    "arrival": round(r["arrival"], 1) if isinstance(r.get("arrival"), (int, float)) else r.get("arrival"),
                    "start": round(r["start"], 1) if isinstance(r.get("start"), (int, float)) else r.get("start"),
                    "depart": round(r["depart"], 1) if isinstance(r.get("depart"), (int, float)) else r.get("depart"),
                    "wait": round(r["wait"], 1) if isinstance(r.get("wait"), (int, float)) else r.get("wait"),
                    "load_after": round(r["load_after"], 1) if isinstance(r.get("load_after"), (int, float)) else r.get("load_after"),
                    "window": win,
                    "status": "pending",
                })
                seq += 1

    return pd.DataFrame(rows, columns=columns)


def comparison_table(rows: List[dict]) -> Any:
    """DataFrame from comparison rows (delivery, status, vehicle_before, vehicle_after, eta_before, eta_after, reason)."""
    if not HAS_PANDAS:
        raise ImportError("pandas is required for export functions. Install with: pip install pandas")
    columns = [
        "delivery", "status", "vehicle_before", "vehicle_after",
        "eta_before", "eta_after", "reason"
    ]
    if not rows:
        return pd.DataFrame(columns=columns)

    extracted = []
    for r in rows:
        extracted.append({
            "delivery": r.get("delivery"),
            "status": r.get("status"),
            "vehicle_before": r.get("vehicle_before"),
            "vehicle_after": r.get("vehicle_after"),
            "eta_before": r.get("eta_before"),
            "eta_after": r.get("eta_after"),
            "reason": r.get("reason"),
        })
    return pd.DataFrame(extracted, columns=columns)


def unfulfilled_table(plan: Plan, env: Env) -> Any:
    """DataFrame: delivery_id, location, weight, window, reason, proven."""
    if not HAS_PANDAS:
        raise ImportError("pandas is required for export functions. Install with: pip install pandas")
    columns = ["delivery_id", "location", "weight", "window", "reason", "proven"]
    records = []
    if hasattr(plan, "unassigned") and plan.unassigned:
        for did in sorted(plan.unassigned.keys()):
            info = plan.unassigned[did]
            d = env.deliveries.get(did) if hasattr(env, "deliveries") else None
            loc = d.location if d else None
            wt = d.weight if d else None
            win = f"{fmt_time(d.tw_start)}-{fmt_time(d.tw_end)}" if d else ""
            reason = info.get("reason", "") if isinstance(info, dict) else str(info)
            proven = bool(info.get("proven", False)) if isinstance(info, dict) else False
            records.append({
                "delivery_id": did,
                "location": loc,
                "weight": wt,
                "window": win,
                "reason": reason,
                "proven": proven,
            })
    return pd.DataFrame(records, columns=columns)


def export_csv(df: Any) -> str:
    """Convert a DataFrame to CSV string."""
    if not HAS_PANDAS:
        raise ImportError("pandas is required for export functions. Install with: pip install pandas")
    return df.to_csv(index=False)


def export_excel(dfs: Dict[str, Any]) -> bytes:
    """Convert multiple DataFrames into a multi-sheet Excel file (bytes)."""
    if not HAS_PANDAS:
        raise ImportError("pandas is required for export functions. Install with: pip install pandas")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as writer:
        if not dfs:
            pd.DataFrame().to_excel(writer, sheet_name="Sheet1")
        else:
            for sheet_name, df in dfs.items():
                df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    return buf.getvalue()
