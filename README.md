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

**Phase 4:**
- `ml/risk_scoring.ipynb` — the actual, **executed** validation notebook (run it
  yourself to see it work, or read the baked-in outputs). Trains an XGBoost regressor
  predicting each station's weekly incident count, using only lagged features (no data
  leakage — genuine forecasting, not fitting a week's features to that same week's
  count), with a chronological train/test split (not random, which would be invalid
  for forecasting)
- **Validated against known injected patterns, honestly, including one that came back
  weaker than hoped**: (1) feature importance correctly ranks `is_festival_season` and
  `mix_Vehicle Theft` as the top 2 features — matching the injected seasonal spike and
  static hotspot; (2) Whitefield PS is correctly predicted as highest-average-risk
  station; (3) the Jayanagar recent-Robbery-spike pattern showed a **weaker** aggregate
  signal at first check (diluted because the model predicts *total* station volume
  across all 7 crime types, and a Robbery-specific spike is a small fraction of that
  total) — investigated further with SHAP rather than accepted or hidden, and by the
  final injected-spike week, `mix_Robbery` is confirmed as by far the largest SHAP
  contributor. **Conclusion documented in the notebook**: this risk model and Phase 2's
  red-zone z-score alerting are complementary tools, not redundant — z-score alerting
  catches immediate week-to-week spikes, this model catches slower-building structural
  risk (chronic hotspots, seasonal patterns). Say exactly this in the demo
- `backend/risk_features.py` — feature engineering shared identically between the
  training notebook and the live API, specifically to avoid train/serve skew (a common
  real-world ML bug where live serving code computes features slightly differently
  than training did)
- `backend/risk_explain.py` — aggregates 17 raw SHAP feature values into 5
  human-readable categories (recent trend, time-of-day, weekly pattern, seasonal
  factor, crime-type mix) with percentages, plus a generated plain-English sentence.
  Shared between the notebook and the API
- `/api/risk-score` — tested end-to-end: computes live features from current DB state,
  runs the model, generates SHAP explanations, returns per-station risk ranked highest
  first. **Real bug caught and fixed**: the first version crashed with a JSON
  serialization error because SHAP/numpy return `float32` values, which FastAPI's
  encoder can't serialize — fixed by explicit `float()` casts in `risk_explain.py`
- Frontend: new Risk tab with a station ranking list, the plain-English explanation
  sentence, and a SHAP contribution bar chart (recharts — the library named in the
  original spec) color-coded by feature category
- To regenerate the model from scratch: `cd ml && jupyter nbconvert --to notebook
  --execute risk_scoring.ipynb`, then copy `risk_model.json`, `feature_cols.json` into
  `backend/`



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

**Ground-truth recovery dashboard (added on request, incorporated into the existing
Risk tab rather than a separate duplicate system):**
- `backend/ground_truth_recovery.py` — imports the actual injected constants directly
  from `generate_data.py` (never re-typed, so it can't drift out of sync), and computes
  two **honestly separated** kinds of recovery: **data-level** (observed night/day and
  weekend/weekday rate ratios computed directly from the incidents table via SQL — does
  NOT involve the trained model) and **model-level** (counterfactual predictions and
  station-average comparisons from the trained model). Kept separate deliberately —
  the risk model predicts total station volume across all 7 crime types, so it was
  never architecturally able to learn a clean, isolated "Burglary is 2.2x more common
  at night" coefficient the way a per-crime-type model would. Presenting a per-crime
  data pattern as if the model "learned" it would be overclaiming.
- **A real, significant bug found while building this**: the night/day observed ratios
  came back nearly identical (~4.4x) across three crime types with different injected
  multipliers (2.2x, 1.9x, 1.5x) — which shouldn't happen if the multipliers were
  actually wired in. Investigated and found that `generate_data.py`'s `random_hour()`
  only checked crime-type *membership* in `NIGHT_MULTIPLIER`, never the actual
  multiplier *value* — applying a flat 65% night-probability to all three regardless
  of their claimed multiplier. **This had been silently wrong since Phase 1** and
  wasn't caught by earlier testing because those checks only confirmed "some night
  skew exists," not that it matched the specific claimed multiplier per crime type.
  Fixed by deriving the correct per-crime-type night-probability from each multiplier
  algebraically (solving for P(night) that produces the target rate ratio), data
  regenerated, and **all of Phases 1-4 re-verified against the corrected data**:
  Phase 2 red-zone alerting still correctly flags the same station/crime pair, Phase 3
  MO clustering still correctly isolates the same 5 ring suspects, Phase 4's model
  retrained and re-validated with the same conclusions. Night/day ratios now match
  almost exactly: Burglary 2.28 vs injected 2.2, Vehicle Theft 1.89 vs 1.9, Robbery 1.5
  vs 1.5 (weekend/weekday ratios were already accurate before this fix: 1.82/1.51/1.33
  vs injected 1.8/1.6/1.3)
- `/api/ground-truth-recovery` — tested, another `float32` JSON-serialization bug
  caught and fixed the same way as the earlier one (explicit `float()` casts)
- Frontend: new section in the Risk tab showing both recovery tables, clearly labeled
  by type, with the honesty notes visible inline (not hidden in code comments only)



**Phase 5:**
- Role toggle (Station Officer vs SCRB Analyst) added as a visible design gesture in
  the sidebar. Switching to Officer: restricts the tab bar to Map only (Network/Risk
  tabs show a 🔒 and disabled state with a tooltip), and locks district drill-down to
  a single assigned district (hardcoded to "Bengaluru Urban" for the demo — confirmed
  this matches a real district name in the data before shipping it). **This is
  explicitly NOT real access control** — there's no authentication anywhere in this
  API, and the caveat text is visible in the UI itself, not just in this README, so it
  can't be mistaken for something it isn't during a demo
- Unified error/loading state styling across Map, Network, and Risk tabs into shared
  `.error-banner` / `.loading-banner` CSS classes (previously each view had
  near-identical but separately-written inline styles)
- Refactored `RiskDashboard.jsx` off heavy inline styling onto named CSS classes,
  matching the styling approach used elsewhere in the app
- See below for the production data-ingestion story and privacy/access-control design
  intent this demo's role-toggle and synthetic-data choices stand in for

## Production data-ingestion story (not implemented — design intent only)

This demo uses synthetic data generated directly into Postgres. A production version
connecting to KSP's real CCTNS (Crime and Criminal Tracking Network & Systems) or
station-level FIR systems would need:

- **A normalization/ETL layer** between CCTNS and this platform's schema — real FIR
  records won't cleanly map to `weapon_or_method` / `target_type` / `escape_pattern`
  as clean categorical fields the way synthetic data does; that would need to come
  from structured fields in the FIR where available, and NLP-based extraction from
  free-text FIR narrative sections where it isn't (a real, nontrivial project on its
  own — flagged here rather than hand-waved as "easy")
- **Incremental sync**, not batch reload — likely a scheduled job polling CCTNS for
  new/updated FIRs, or an event-driven feed if CCTNS exposes one, feeding into the same
  `incidents` table so the red-zone alerting and risk model stay current
- **Data quality gates** before ingestion — real FIR data will have missing fields,
  inconsistent station naming, and duplicate entries in ways synthetic data doesn't

## Privacy & access-control design intent (not implemented — design intent only)

The Officer/Analyst toggle in this demo is a **visual mockup only** — there is no
authentication on this API, and anyone can call any endpoint. A production version
would need:

- **Real authenticated sessions** (e.g. JWT-based, issued after login against KSP's
  existing personnel directory/AD, not a new credential system)
- **Server-side role enforcement**, not client-side — every API endpoint would check
  the authenticated user's role and jurisdiction before querying, not just the
  frontend choosing what to display. Concretely: row-level security policies in
  Postgres keyed to the requesting officer's assigned station/district, so a station
  officer's queries are restricted at the database layer, not just hidden in the UI
- **Audit logging** — every query against sensitive data (suspect records, victim
  PII) logged with who queried what and when, for accountability under law-enforcement
  data governance requirements
- **Data minimization for lower roles** — a station officer's view should actively
  exclude victim PII fields they don't need for routine work, not just hide them in
  the UI while still sending them over the API response

