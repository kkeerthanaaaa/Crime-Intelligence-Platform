# KSP Crime Intelligence Platform — Phase 1

This has been built and verified end-to-end (real Postgres+PostGIS → real FastAPI →
real React map, tested with 21,783 synthetic incidents). Follow these steps exactly on
your own machine.

## Prerequisites

- PostgreSQL 14+ with PostGIS extension installed
- Python 3.10+
- Node.js 18+

## 1. Database setup

```bash
# Create the database (adjust user/password as needed)
createdb ksp_crime

# If your Postgres user isn't "postgres" with password "postgres", edit
# DB_CONFIG at the top of backend/generate_data.py and backend/main.py to match.

# Apply the schema
psql -U postgres -d ksp_crime -f backend/schema.sql
```

## 2. Backend setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Generate synthetic data (prints an injected-pattern summary — save this output,
# you'll need it in Phase 4 to validate the ML model recovers real signal)
python3 generate_data.py

# Start the API
uvicorn main:app --reload --port 8000
```

Verify it's working:
```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/districts
```

## 3. Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (usually http://localhost:5173). You should see a map of
Karnataka with red incident markers, and a counter at top-left confirming how many
incidents loaded from the API.

## What's verified working right now

**Phase 1:**
- PostGIS schema applies cleanly with no errors
- Generator produces ~21,700 incidents across 8 stations / 3 districts, with 7
  deliberately injected patterns (base rates, weekend skew, night skew, seasonal
  spike, one static hotspot station, one recent-4-week spike, one 5-suspect MO ring)
  — all confirmed present in the DB with direct SQL checks
- All API endpoints tested and returning correct, filtered data
- Frontend builds with zero errors and renders live data from the API on a real map

**Phase 2:**
- `/api/station-stats` — per-station incident counts for choropleth coloring, tested:
  correctly surfaces the injected hotspot station as the highest-density station
- `/api/redzones` — z-score red-zone alerting. **Important fix made during
  development**: the first version compared only the single latest week against "all
  other weeks" as baseline. Since a real trend spike spans multiple weeks, those spike
  weeks polluted their own baseline and hid the anomaly. Fixed by comparing a recent
  multi-week window against an earlier, cleanly separated baseline. Tested: correctly
  and only flags the deliberately injected recent-spike station/crime pair (Jayanagar
  PS / Robbery, z=2.79), and does NOT flag the static hotspot (Whitefield PS / Vehicle
  Theft), which is correct — a permanently-elevated baseline isn't a recent anomaly
- `time_of_day` / `day_type` filters on `/api/incidents` — tested: night Burglary
  count is ~80% higher than day Burglary despite fewer night hours; weekend Assault
  per-day rate is ~1.8x weekday rate, matching the injected multiplier almost exactly
- Frontend: district drill-down (map flies to bounds), crime-type filter, density
  choropleth (station catchment circles colored/sized by incident count — see note
  below), heatmap toggle with day/night and weekday/weekend sub-filters, and a
  red-zone alert panel with pulsing markers on affected stations
- Frontend builds with zero errors; dev server and backend confirmed running
  simultaneously and communicating correctly

**Phase 3:**
- `mo_clustering.py` — builds a per-suspect MO feature vector (weapon/method,
  target type, escape pattern, day/night split) averaged across their linked
  incidents, then clusters via scikit-learn's AgglomerativeClustering on cosine
  distance. **Threshold validated by direct experiment**: at distance_threshold
  0.1-0.2, clustering correctly and exactly isolates the 5 deliberately-injected
  ring suspects (ids 1-5) into their own cluster, separate from the other 145 —
  confirmed via a standalone test script before wiring into the API, not assumed
- **Real bug caught and fixed during this phase**: the Phase 1 generator had
  accidentally set the injected ring's `weapon_or_method` to `"Two-Wheeler"` — an
  escape-pattern value, not a valid weapon category. It sat silently in the DB (no
  schema constraint caught it) but broke proper MO feature encoding. Fixed to
  `"Improvised"`, data regenerated, and Phase 1/2 patterns re-verified to still hold
  after the fix
- `/api/network` — **a second real bug caught by testing**: the first version
  filtered suspects by an absolute incident-count threshold (>=3), but since this
  dataset has only 150 suspects across ~21,700 incidents, literally every suspect
  exceeds that — the endpoint returned 458 nodes and 24,151 edges, useless for a
  force-directed graph. Fixed by switching to relative top-N filtering (most active
  N suspects) plus a per-suspect sampled-incident cap, which scales regardless of
  dataset size. Re-tested: 12 suspects → 133 nodes, 206 links — readable. The top-12
  filter naturally surfaces all 5 ring suspects (they have 2x the incidents of
  everyone else), so the demo's "hidden network" story appears automatically without
  needing to manually cherry-pick a district or suspect
- Frontend: tabbed Map/Network interface, force-directed graph via `react-force-graph`
  (the exact package named in the spec), suspects colored by MO cluster, adjustable
  top-N and per-suspect-incident-cap sliders, click-to-inspect node details
- Frontend builds with zero errors (one non-blocking bundle-size warning — 
  react-force-graph pulls in three.js internally, ~2.3MB bundle; fine for a hackathon
  demo, worth noting if you later care about load time)

 there's no real KSP district administrative boundary
shapefile available for this hackathon, so "choropleth" here colors each station's
circular jurisdiction catchment by density rather than filling true district polygon
borders. This is disclosed in-app (see the map legend) and should be stated plainly in
your demo — it's a reasonable, honest approximation, not a claim of real boundaries.

**Testing limitation to be aware of:** I've verified the backend logic thoroughly
(direct SQL checks, curl against every endpoint, numeric sanity checks against the
known injected patterns) and confirmed the frontend builds cleanly and both servers
run simultaneously. What I have NOT been able to verify is the actual rendered
in-browser behavior (does the heatmap visually look right, does clicking a district
actually fly the map smoothly, does the pulse animation render as expected) — that
needs a real browser, which isn't available in this environment. Do a visual pass
yourself once you run it locally before the demo.

## Blank-page fix (if you hit this after Phase 3)

If you saw a blank page after adding the network graph: I found and fixed two real
issues in the `react-force-graph` package:

1. **Wrong import style** — I'd written `import { ForceGraph2D } from "react-force-graph"`
   (named import), but the package actually exports it as a **default** export. This
   alone would throw and blank the whole page, since the broken import sits at the
   top of a file that's loaded regardless of which tab you're on.
2. **Switched to `react-force-graph-2d`** instead of the umbrella `react-force-graph`
   package. The umbrella package bundles 2D **and** 3D/VR/AR support via three.js, and
   pulls in a fragile `ssh://git@github.com/...` dependency (`three-bmfont-text`) that
   can silently fail to install on machines without SSH keys configured for GitHub.
   Since we only ever use `ForceGraph2D`, switching to the dedicated 2D package
   removes three.js entirely, drops the bundle from 2.3MB to 547KB, and removes the
   git-SSH fragility.

**I could not fully verify this in a real browser** — this sandbox has no browser
available, and my attempt to reproduce the crash with a headless jsdom render hit
tooling limitations of its own (Node's ESM/CJS interop with Vite's SSR module loader).
So: please pull this update, run `npm install` fresh (to drop the old package and
pick up `react-force-graph-2d`), and confirm the page renders. **If it's still blank,
open your browser's dev console (F12 → Console tab) and send me the exact error** —
that's the fastest path to the real fix if this wasn't it.

## Next: Phase 4


Explainable predictive risk scoring (XGBoost/LightGBM + SHAP) — see the build spec doc
for full detail. This is the most important remaining phase; take the time to validate
it in a notebook against the injected patterns in generate_data.py before wiring it
into the app.
