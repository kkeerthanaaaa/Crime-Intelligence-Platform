"""
KSP Crime Intelligence Platform — Phase 1 API
Serves incidents (filterable) and station jurisdictions as GeoJSON.
"""

from datetime import datetime
from typing import Optional
from collections import defaultdict

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from mo_clustering import compute_mo_clusters

DB_CONFIG = dict(
    dbname="ksp_crime", user="postgres", password="postgres",
    host="localhost", port=5432,
)

app = FastAPI(title="KSP Crime Intelligence API")

# Wide open for hackathon dev; tighten this before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_conn():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/incidents")
def get_incidents(
    station_id: Optional[int] = None,
    district: Optional[str] = None,
    crime_type: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    time_of_day: Optional[str] = Query(default=None, regex="^(day|night)$"),
    day_type: Optional[str] = Query(default=None, regex="^(weekday|weekend)$"),
    limit: int = Query(default=5000, le=20000),
):
    """Return incidents as a filterable list. Frontend renders these as map/heatmap points.

    time_of_day: 'night' = 22:00-04:59, 'day' = 05:00-21:59
    day_type: 'weekend' = Sat/Sun, 'weekday' = Mon-Fri
    """
    clauses, params = [], []

    if station_id is not None:
        clauses.append("i.station_id = %s")
        params.append(station_id)
    if district is not None:
        clauses.append("s.district = %s")
        params.append(district)
    if crime_type is not None:
        clauses.append("i.crime_type = %s")
        params.append(crime_type)
    if date_from is not None:
        clauses.append('i."timestamp" >= %s')
        params.append(date_from)
    if date_to is not None:
        clauses.append('i."timestamp" <= %s')
        params.append(date_to)
    if time_of_day == "night":
        clauses.append('(EXTRACT(HOUR FROM i."timestamp") >= 22 OR EXTRACT(HOUR FROM i."timestamp") < 5)')
    elif time_of_day == "day":
        clauses.append('(EXTRACT(HOUR FROM i."timestamp") >= 5 AND EXTRACT(HOUR FROM i."timestamp") < 22)')
    if day_type == "weekend":
        clauses.append('EXTRACT(DOW FROM i."timestamp") IN (0, 6)')
    elif day_type == "weekday":
        clauses.append('EXTRACT(DOW FROM i."timestamp") NOT IN (0, 6)')

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT i.id, i.station_id, s.name AS station_name, s.district,
               i.lat, i.long, i.crime_type, i."timestamp",
               i.weapon_or_method, i.target_type, i.escape_pattern
        FROM incidents i
        JOIN stations s ON s.id = i.station_id
        {where_sql}
        ORDER BY i."timestamp" DESC
        LIMIT %s
    """
    params.append(limit)

    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
    conn.close()
    return {"count": len(rows), "incidents": rows}


@app.get("/api/station-stats")
def get_station_stats(
    crime_type: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
):
    """Per-station incident counts, for choropleth coloring of station catchments.

    Note: we don't have real district administrative boundary polygons (no shapefile
    for this hackathon), so 'choropleth' here colors each station's jurisdiction
    catchment circle by its incident density rather than filling true district
    borders. This is disclosed in the README/pitch — it's an honest approximation,
    not a claim of real administrative boundaries.
    """
    clauses, params = [], []
    if crime_type is not None:
        clauses.append("i.crime_type = %s")
        params.append(crime_type)
    if date_from is not None:
        clauses.append('i."timestamp" >= %s')
        params.append(date_from)
    if date_to is not None:
        clauses.append('i."timestamp" <= %s')
        params.append(date_to)
    where_sql = f"AND {' AND '.join(clauses)}" if clauses else ""

    query = f"""
        SELECT s.id, s.name, s.district, s.lat, s.long,
               COUNT(i.id) AS incident_count
        FROM stations s
        LEFT JOIN incidents i ON i.station_id = s.id {where_sql}
        GROUP BY s.id, s.name, s.district, s.lat, s.long
        ORDER BY incident_count DESC
    """
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
    conn.close()
    return {"stations": rows}


@app.get("/api/redzones")
def get_redzones(z_threshold: float = 2.0, current_window_weeks: int = 3):
    """Red-zone alerting: for each (station, crime_type) pair, bucket incidents into
    weekly counts. Compare the average weekly count over the most recent
    `current_window_weeks` weeks against the mean/std of all earlier weeks (the
    baseline). Flag the pair if the recent average exceeds baseline by more than
    z_threshold standard deviations.

    Important design note: we deliberately compare a recent WINDOW (not a single
    latest week) against a baseline that EXCLUDES that whole window. An earlier
    version compared only the single most recent week against "all other weeks" —
    but a real trend spike spans multiple weeks, so those spike weeks ended up
    inside their own baseline and diluted the z-score, hiding the anomaly. Comparing
    windows to a cleanly separated baseline avoids that.

    Requires at least current_window_weeks + 5 weeks of total history to establish a
    meaningful baseline.
    """
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT s.id AS station_id, s.name AS station_name, s.district,
                   i.crime_type,
                   date_trunc('week', i."timestamp") AS week,
                   COUNT(*) AS incident_count
            FROM incidents i
            JOIN stations s ON s.id = i.station_id
            GROUP BY s.id, s.name, s.district, i.crime_type, week
            ORDER BY s.id, i.crime_type, week
        """)
        rows = cur.fetchall()
    conn.close()

    import numpy as np
    from collections import defaultdict

    grouped = defaultdict(list)
    for r in rows:
        key = (r["station_id"], r["station_name"], r["district"], r["crime_type"])
        grouped[key].append((r["week"], r["incident_count"]))

    redzones = []
    for (station_id, station_name, district, crime_type), weeks in grouped.items():
        weeks.sort(key=lambda w: w[0])
        min_weeks_needed = current_window_weeks + 5
        if len(weeks) < min_weeks_needed:
            continue  # not enough history to establish a baseline

        current_weeks = weeks[-current_window_weeks:]
        baseline_weeks = weeks[:-current_window_weeks]

        baseline_counts = [w[1] for w in baseline_weeks]
        mean = float(np.mean(baseline_counts))
        std = float(np.std(baseline_counts))
        if std == 0:
            continue  # no variance to compute a meaningful z-score against

        current_avg = float(np.mean([w[1] for w in current_weeks]))
        z = (current_avg - mean) / std
        if z > z_threshold:
            redzones.append({
                "station_id": station_id,
                "station_name": station_name,
                "district": district,
                "crime_type": crime_type,
                "current_window_weeks": current_window_weeks,
                "current_avg_weekly_count": round(current_avg, 2),
                "baseline_mean": round(mean, 2),
                "baseline_std": round(std, 2),
                "z_score": round(z, 2),
            })

    redzones.sort(key=lambda r: r["z_score"], reverse=True)
    return {"threshold": z_threshold, "current_window_weeks": current_window_weeks, "redzones": redzones}


@app.get("/api/mo-clusters")
def get_mo_clusters(min_incidents: int = 1):
    """MO clustering: groups suspects by cosine similarity of their weapon/target/
    escape-pattern/time-of-day pattern across their linked incidents. See
    mo_clustering.py for the threshold-validation note.
    """
    conn = get_conn()
    clusters = compute_mo_clusters(conn, min_incidents=min_incidents)

    # Pull suspect names for display
    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM suspects WHERE id = ANY(%s)", (list(clusters.keys()),))
        names = {r["id"]: r["name"] for r in cur.fetchall()}
    conn.close()

    out = []
    for sid, info in clusters.items():
        out.append({"suspect_id": sid, "name": names.get(sid, f"Suspect {sid}"), **info})
    out.sort(key=lambda r: (r["cluster_id"], -r["incident_count"]))

    # Only surface clusters with more than one member — a cluster of size 1 isn't a
    # pattern, it's just an individual with no one to compare against.
    cluster_sizes = {}
    for r in out:
        cluster_sizes[r["cluster_id"]] = cluster_sizes.get(r["cluster_id"], 0) + 1
    multi_member_clusters = [r for r in out if cluster_sizes[r["cluster_id"]] > 1]

    return {
        "total_suspects_clustered": len(out),
        "clusters_found": len(set(r["cluster_id"] for r in out)),
        "multi_member_clusters": multi_member_clusters,
    }


@app.get("/api/network")
def get_network(top_n_suspects: int = 12, max_incidents_per_suspect: int = 8, district: Optional[str] = None):
    """Returns a suspect/victim/station graph as nodes+links for react-force-graph.

    FILTERING DESIGN NOTE — this was changed after testing surfaced a real problem:
    an earlier version filtered by an absolute `min_suspect_incidents` threshold
    (e.g. >= 3 incidents). But this dataset has only 150 suspects across ~21,700
    incidents, so EVERY suspect has 100+ linked incidents — an absolute threshold
    filters out nobody, and the endpoint returned 458 nodes / 24,151 edges, which is
    unreadable in any force-directed graph. Fixed by switching to relative filtering:
    (1) `top_n_suspects` selects only the N most active suspects by incident count,
    which scales regardless of dataset size, and (2) `max_incidents_per_suspect`
    samples a bounded number of each suspect's incidents for edges, so the graph
    stays visually tractable even if a suspect has hundreds of linked incidents.
    This means the graph shows a representative sample of each top suspect's
    connections, not their full edge list — stated here and in the frontend legend.
    """
    conn = get_conn()

    clusters = compute_mo_clusters(conn, min_incidents=1)

    clauses = []
    params = []
    if district:
        clauses.append("s.district = %s")
        params.append(district)
    where_sql = f"AND {' AND '.join(clauses)}" if clauses else ""

    with conn.cursor() as cur:
        # Pick the top N most active suspects (optionally within a district)
        cur.execute(f"""
            SELECT isx.suspect_id, COUNT(*) AS incident_count
            FROM incident_suspects isx
            JOIN incidents i ON i.id = isx.incident_id
            JOIN stations s ON s.id = i.station_id
            WHERE 1=1 {where_sql}
            GROUP BY isx.suspect_id
            ORDER BY incident_count DESC
            LIMIT %s
        """, params + [top_n_suspects])
        top_suspects = [r["suspect_id"] for r in cur.fetchall()]

        if not top_suspects:
            conn.close()
            return {"nodes": [], "links": [], "top_n_suspects": top_n_suspects}

        # For each top suspect, sample up to max_incidents_per_suspect incidents
        cur.execute("""
            SELECT isx.suspect_id, sus.name AS suspect_name,
                   i.id AS incident_id, i.crime_type, i.station_id, s.name AS station_name,
                   ivx.victim_id, vic.name AS victim_name,
                   ROW_NUMBER() OVER (PARTITION BY isx.suspect_id ORDER BY i."timestamp" DESC) AS rn
            FROM incident_suspects isx
            JOIN suspects sus ON sus.id = isx.suspect_id
            JOIN incidents i ON i.id = isx.incident_id
            JOIN stations s ON s.id = i.station_id
            LEFT JOIN incident_victims ivx ON ivx.incident_id = i.id
            LEFT JOIN victims vic ON vic.id = ivx.victim_id
            WHERE isx.suspect_id = ANY(%s)
        """, (top_suspects,))
        all_rows = cur.fetchall()
    conn.close()

    # Apply the per-suspect incident cap in Python (simplest correct way to combine
    # "top N distinct incidents per suspect" with "may have multiple victim rows
    # per incident" from the LEFT JOIN)
    seen_incidents_per_suspect = defaultdict(set)
    rows = []
    for r in all_rows:
        key = (r["suspect_id"], r["incident_id"])
        if r["incident_id"] not in seen_incidents_per_suspect[r["suspect_id"]]:
            if len(seen_incidents_per_suspect[r["suspect_id"]]) >= max_incidents_per_suspect:
                continue
            seen_incidents_per_suspect[r["suspect_id"]].add(r["incident_id"])
        rows.append(r)

    nodes = {}
    edges = {}

    def add_node(node_id, node_type, label, extra=None):
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "type": node_type, "label": label, **(extra or {})}

    def add_edge(source, target, relation):
        key = (source, target, relation)
        if key not in edges:
            edges[key] = {"source": source, "target": target, "relation": relation, "weight": 0}
        edges[key]["weight"] += 1

    for r in rows:
        suspect_node = f"suspect-{r['suspect_id']}"
        station_node = f"station-{r['station_id']}"
        cluster_info = clusters.get(r["suspect_id"], {})
        add_node(suspect_node, "suspect", r["suspect_name"], {
            "cluster_id": cluster_info.get("cluster_id"),
            "dominant_weapon": cluster_info.get("dominant_weapon"),
            "total_incident_count": cluster_info.get("incident_count"),
        })
        add_node(station_node, "station", r["station_name"])
        add_edge(suspect_node, station_node, "occurred_at")

        if r["victim_id"] is not None:
            victim_node = f"victim-{r['victim_id']}"
            add_node(victim_node, "victim", r["victim_name"])
            add_edge(suspect_node, victim_node, "victim_of")

    return {
        "nodes": list(nodes.values()),
        "links": list(edges.values()),
        "top_n_suspects": top_n_suspects,
        "max_incidents_per_suspect": max_incidents_per_suspect,
    }


@app.get("/api/stations")
def get_stations():
    """Return station jurisdictions as GeoJSON FeatureCollection."""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, name, district, lat, long,
                   ST_AsGeoJSON(jurisdiction_polygon) AS geom
            FROM stations
        """)
        rows = cur.fetchall()
    conn.close()

    features = []
    for r in rows:
        import json
        features.append({
            "type": "Feature",
            "geometry": json.loads(r["geom"]),
            "properties": {
                "id": r["id"], "name": r["name"], "district": r["district"],
                "lat": r["lat"], "long": r["long"],
            },
        })
    return {"type": "FeatureCollection", "features": features}


@app.get("/api/districts")
def get_districts():
    """Distinct districts and crime types — for populating frontend filter dropdowns."""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT district FROM stations ORDER BY district")
        districts = [r["district"] for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT crime_type FROM incidents ORDER BY crime_type")
        crime_types = [r["crime_type"] for r in cur.fetchall()]
    conn.close()
    return {"districts": districts, "crime_types": crime_types}
