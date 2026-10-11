# DISHA — ReRoute · CascadeGuard

> **Don't just reroute the vehicle. Prevent the chain reaction.**

DISHA is a fleet-disruption recovery platform for dispatchers. Its engine, **ReRoute**, replans deliveries when something goes wrong (breakdown, road closure, urgent order) and explains every decision. **CascadeGuard** is the idea behind it: one incident should not silently snowball across the fleet.

## Why

A vehicle breaks down at 11:30 AM. Moving its stops to another vehicle delays that vehicle's next stop, which misses its window, which makes a later delivery impossible, which pulls in a third vehicle. One incident, a chain reaction. DISHA lets a dispatcher **see the consequences before applying a change** and keep the damage small.

## USPs

- **Counterfactual Replanning (flagship):** compare genuinely different recovery options and see why the chosen one wins.
- **Preview before commit:** every incident is previewed and validated; the live plan only changes when the dispatcher applies it.
- **Delivery Promise Protection:** time windows, capacity and shift end are hard constraints. Orders that cannot be saved are flagged with a reason, never silently promised.
- **Kept / Moved / Broken view:** each order is classified so the real impact of a disruption is visible at a glance.
- **Independent validator:** a separate checker re-verifies every plan, with fallback to the last valid plan.
- **Resilience-Aware Routing (roadmap):** test plans against simulated future disruptions.

## Features

- Initial plan generation (insertion-based heuristic)
- Incidents: vehicle failure (including mid-leg), road closures, urgent orders, shift-end limits
- Plain-text incident input ("truck 2 stopped at Depot B") with deterministic parsing and optional Groq fallback; text incidents always need confirmation
- Cargo recovery after breakdown (explicit pickup stop, capacity-checked)
- Proven vs heuristic infeasibility reasons for unserved orders
- Undo, time advance, saved scenarios, decision report
- CSV / Excel export
- Dispatcher dashboard (Leaflet map, configurable tile provider)

## Project Structure

```
disha/
├── backend/             # Python 3.11+ engine and API
│   ├── reroute/         # planner, replan, validator, compare, incidents, server
│   ├── web/             # built-in HTML dashboard served by the API
│   ├── data/            # demo scenario
│   ├── scripts/         # demo generator
│   ├── tests/
│   └── run_tests.py
├── frontend/            # React + TanStack Start dispatcher UI
├── .env.example
└── README.md
```

## Setup

```bash
cp .env.example .env                       # add GROQ_API_KEY
cp frontend/.env.example frontend/.env     # optional map tile provider
```

**Backend**
```bash
cd backend
pip install -r requirements.txt
python run_tests.py                        # 102 tests
python -m reroute.server                   # http://127.0.0.1:8000
```

**Frontend**
```bash
cd frontend
bun install        # or npm install
bun run dev
```

## Environment Variables

| Variable | Where | Purpose |
|---|---|---|
| `GROQ_API_KEY` | `.env` | Enables AI incident parsing and message polish via Groq |
| `GROQ_MODEL` | `.env` | Groq model (default `llama-3.3-70b-versatile`) |
| `VITE_MAP_TILE_URL` | `frontend/.env` | Map tile URL (Mapbox, MapTiler, etc.). Empty = OpenStreetMap |

Without a Groq key everything still works using the deterministic parser.

## Status

Backend engine, validator, comparison, incidents and the built-in dashboard are working and tested. The React frontend is a UI shell and is not yet connected to the backend API. Cascade-chain visualization, multi-plan counterfactual comparison and resilience scoring are the next milestones.

## Assumptions

- Travel times come from a simulated matrix (no live traffic or GPS).
- The planner is a greedy heuristic: valid, not guaranteed optimal.
- Hard time windows are never shown as guaranteed when no feasible plan exists.
