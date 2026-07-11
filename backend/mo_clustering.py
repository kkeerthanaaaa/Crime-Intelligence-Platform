"""
MO (Modus Operandi) clustering for the KSP Crime Intelligence Platform.

Builds a feature vector per suspect from their linked incidents (weapon/method,
target type, escape pattern, day/night split), then clusters suspects by cosine
similarity using scikit-learn's AgglomerativeClustering.

THRESHOLD VALIDATION NOTE: distance_threshold=0.15 was chosen by direct experiment
against this project's synthetic data, which has a deliberately injected 5-suspect
MO ring (see generate_data.py pattern 7). At threshold 0.1-0.2, clustering correctly
isolates exactly those 5 suspects into their own cluster, separate from the other
145. Below ~0.1 the ring itself started fragmenting; above ~0.25 everything
collapsed into a single cluster. If you regenerate data with different injected
patterns, re-validate this threshold rather than assuming it still holds.
"""

from collections import defaultdict

import numpy as np
import psycopg2.extras
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity

WEAPONS = ["None", "Knife", "Blunt Object", "Firearm", "Improvised"]
TARGETS = ["Residence", "Commercial", "Vehicle", "Individual", "Public Space"]
ESCAPES = ["On Foot", "Two-Wheeler", "Car", "Public Transport", "Unknown"]
VECTOR_DIM = len(WEAPONS) + len(TARGETS) + len(ESCAPES) + 2  # +2 for day/night

DISTANCE_THRESHOLD = 0.15


def _build_feature_vector(records):
    """Average one-hot MO encoding across a suspect's incidents."""
    vec = np.zeros(VECTOR_DIM)
    for r in records:
        vec[WEAPONS.index(r["weapon_or_method"])] += 1
        vec[len(WEAPONS) + TARGETS.index(r["target_type"])] += 1
        vec[len(WEAPONS) + len(TARGETS) + ESCAPES.index(r["escape_pattern"])] += 1
        is_night = 1 if (r["hour"] >= 22 or r["hour"] < 5) else 0
        vec[len(WEAPONS) + len(TARGETS) + len(ESCAPES) + is_night] += 1
    return vec / len(records)


def compute_mo_clusters(conn, min_incidents=1):
    """Returns {suspect_id: {cluster_id, incident_count, dominant_weapon,
    dominant_target, dominant_escape}} for all suspects with >= min_incidents
    linked incidents.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT isx.suspect_id, i.weapon_or_method, i.target_type, i.escape_pattern,
                   EXTRACT(HOUR FROM i."timestamp") AS hour
            FROM incident_suspects isx
            JOIN incidents i ON i.id = isx.incident_id
        """)
        rows = cur.fetchall()

    by_suspect = defaultdict(list)
    for r in rows:
        by_suspect[r["suspect_id"]].append(r)

    suspect_ids = sorted(sid for sid, recs in by_suspect.items() if len(recs) >= min_incidents)
    if len(suspect_ids) < 2:
        return {}

    vectors = np.array([_build_feature_vector(by_suspect[sid]) for sid in suspect_ids])

    similarity = cosine_similarity(vectors)
    distance = np.clip(1 - similarity, 0, None)
    np.fill_diagonal(distance, 0)

    model = AgglomerativeClustering(
        metric="precomputed", linkage="average",
        distance_threshold=DISTANCE_THRESHOLD, n_clusters=None,
    )
    labels = model.fit_predict(distance)

    result = {}
    for sid, label in zip(suspect_ids, labels):
        recs = by_suspect[sid]
        weapon_counts = defaultdict(int)
        target_counts = defaultdict(int)
        escape_counts = defaultdict(int)
        for r in recs:
            weapon_counts[r["weapon_or_method"]] += 1
            target_counts[r["target_type"]] += 1
            escape_counts[r["escape_pattern"]] += 1
        result[sid] = {
            "cluster_id": int(label),
            "incident_count": len(recs),
            "dominant_weapon": max(weapon_counts, key=weapon_counts.get),
            "dominant_target": max(target_counts, key=target_counts.get),
            "dominant_escape": max(escape_counts, key=escape_counts.get),
        }
    return result
