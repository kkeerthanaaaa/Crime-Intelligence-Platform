"""
Synthetic FIR (First Information Report) generator for the KSP Crime Intelligence
Platform demo.

IMPORTANT: This deliberately injects known patterns (weekend/night skew, seasonal
spikes, per-station crime-type base rates) and prints a summary of exactly what was
injected. Keep this printed summary — you'll need it in Phase 4 to prove the ML model
recovers real signal, and to answer "isn't this circular?" from judges.
"""

import random
import numpy as np
from datetime import datetime, timedelta
from faker import Faker
import psycopg2
from psycopg2.extras import execute_values

fake = Faker("en_IN")
random.seed(42)
np.random.seed(42)

DB_CONFIG = dict(
    dbname="ksp_crime", user="postgres", password="postgres",
    host="localhost", port=5432,
)

CRIME_TYPES = ["Theft", "Burglary", "Vehicle Theft", "Assault", "Robbery", "Cybercrime", "Chain Snatching"]
WEAPONS = ["None", "Knife", "Blunt Object", "Firearm", "Improvised"]
TARGET_TYPES = ["Residence", "Commercial", "Vehicle", "Individual", "Public Space"]
ESCAPE_PATTERNS = ["On Foot", "Two-Wheeler", "Car", "Public Transport", "Unknown"]

DISTRICTS = {
    "Bengaluru Urban": [
        ("Cubbon Park PS", 12.9763, 77.5929),
        ("Whitefield PS", 12.9698, 77.7500),
        ("Jayanagar PS", 12.9250, 77.5938),
        ("Yeshwanthpur PS", 13.0284, 77.5540),
    ],
    "Mysuru": [
        ("Devaraja PS", 12.3072, 76.6544),
        ("Krishnaraja PS", 12.3150, 76.6550),
    ],
    "Mangaluru": [
        ("Mangaluru North PS", 12.9165, 74.8560),
        ("Mangaluru South PS", 12.8698, 74.8420),
    ],
}

SIM_START = datetime(2024, 1, 1)
SIM_END = datetime(2025, 12, 31)
TOTAL_DAYS = (SIM_END - SIM_START).days

# --- Deliberately injected patterns (log these; the model must recover them) ---
# 1. Base daily rate per (station, crime_type) — some crime types are just rarer.
BASE_RATE = {
    "Theft": 0.9, "Burglary": 0.5, "Vehicle Theft": 0.6, "Assault": 0.4,
    "Robbery": 0.25, "Cybercrime": 0.35, "Chain Snatching": 0.3,
}
# 2. Weekend multiplier — certain crimes spike on weekends
WEEKEND_MULTIPLIER = {"Assault": 1.8, "Chain Snatching": 1.6, "Theft": 1.3}
# 3. Night-hour multiplier (10pm-4am) — burglary/vehicle theft skew heavily to night
NIGHT_MULTIPLIER = {"Burglary": 2.2, "Vehicle Theft": 1.9, "Robbery": 1.5}
# 4. Seasonal spike — festival season (Oct-Nov) sees a Chain Snatching / Theft spike
SEASONAL_MONTHS = {10, 11}
SEASONAL_MULTIPLIER = {"Chain Snatching": 2.0, "Theft": 1.4}
# 5. One station is deliberately made a "hotspot" for Vehicle Theft to test hotspot detection
HOTSPOT_STATION = "Whitefield PS"
HOTSPOT_CRIME = "Vehicle Theft"
HOTSPOT_MULTIPLIER = 2.5
# 6. A DIFFERENT station gets a sudden RECENT spike (last 4 weeks only) in a different
# crime type — this is distinct from the static hotspot above. The hotspot tests
# "which station has an elevated baseline" (density/choropleth); this recent spike
# tests "which station just changed" (z-score red-zone alerting). Conflating these two
# would leave red-zone alerting with nothing genuine to detect.
RECENT_SPIKE_STATION = "Jayanagar PS"
RECENT_SPIKE_CRIME = "Robbery"
RECENT_SPIKE_MULTIPLIER = 5.0
RECENT_SPIKE_WEEKS = 4


def daily_rate(crime_type, day, station_name):
    rate = BASE_RATE[crime_type]
    is_weekend = day.weekday() >= 5
    if is_weekend:
        rate *= WEEKEND_MULTIPLIER.get(crime_type, 1.0)
    if day.month in SEASONAL_MONTHS:
        rate *= SEASONAL_MULTIPLIER.get(crime_type, 1.0)
    if station_name == HOTSPOT_STATION and crime_type == HOTSPOT_CRIME:
        rate *= HOTSPOT_MULTIPLIER
    if (station_name == RECENT_SPIKE_STATION and crime_type == RECENT_SPIKE_CRIME
            and day >= SIM_END - timedelta(weeks=RECENT_SPIKE_WEEKS)):
        rate *= RECENT_SPIKE_MULTIPLIER
    return rate


def random_hour(crime_type):
    """Pick an hour, skewing certain crime types toward night (22:00-04:00)."""
    if crime_type in NIGHT_MULTIPLIER and random.random() < 0.65:
        return random.choice(list(range(22, 24)) + list(range(0, 5)))
    return random.randint(5, 21)


def jitter(lat, long, meters=800):
    deg = meters / 111_000
    return lat + random.uniform(-deg, deg), long + random.uniform(-deg, deg)


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # --- Insert stations ---
    station_ids = {}
    for district, stations in DISTRICTS.items():
        for name, lat, long in stations:
            cur.execute(
                """INSERT INTO stations (name, district, lat, long, jurisdiction_polygon)
                   VALUES (%s, %s, %s, %s,
                       ST_SetSRID(ST_Buffer(ST_MakePoint(%s, %s)::geography, 2000)::geometry, 4326))
                   RETURNING id""",
                (name, district, lat, long, long, lat),
            )
            station_ids[name] = cur.fetchone()[0]
    conn.commit()

    # --- Insert suspects and victims (pool to reuse across incidents for repeat-offender signal) ---
    N_SUSPECTS = 150
    N_VICTIMS = 300
    suspect_ids = []
    for _ in range(N_SUSPECTS):
        cur.execute("INSERT INTO suspects (name) VALUES (%s) RETURNING id", (fake.name(),))
        suspect_ids.append(cur.fetchone()[0])
    victim_ids = []
    for _ in range(N_VICTIMS):
        cur.execute("INSERT INTO victims (name) VALUES (%s) RETURNING id", (fake.name(),))
        victim_ids.append(cur.fetchone()[0])
    conn.commit()

    # --- Deliberately inject a repeat-offender ring: 5 suspects share the same MO
    # (weapon, target, escape) across multiple stations, so Phase 3's cosine-similarity
    # clustering has real signal to recover. ---
    ring_suspects = suspect_ids[:5]
    RING_MO = dict(weapon_or_method="Improvised", target_type="Commercial", escape_pattern="Two-Wheeler")

    # --- Generate incidents ---
    incidents_created = 0
    incident_rows = []
    for district, stations in DISTRICTS.items():
        for name, lat, long in stations:
            sid = station_ids[name]
            for day_offset in range(TOTAL_DAYS):
                day = SIM_START + timedelta(days=day_offset)
                for crime_type in CRIME_TYPES:
                    rate = daily_rate(crime_type, day, name)
                    count = np.random.poisson(rate)
                    for _ in range(count):
                        hour = random_hour(crime_type)
                        ts = day + timedelta(hours=hour, minutes=random.randint(0, 59))
                        ilat, ilong = jitter(lat, long)
                        weapon = random.choice(WEAPONS)
                        target = random.choice(TARGET_TYPES)
                        escape = random.choice(ESCAPE_PATTERNS)
                        incident_rows.append((sid, ilat, ilong, crime_type, ts, weapon, target, escape))
                        incidents_created += 1

    execute_values(
        cur,
        """INSERT INTO incidents (station_id, lat, long, crime_type, "timestamp",
               weapon_or_method, target_type, escape_pattern)
           VALUES %s RETURNING id""",
        incident_rows,
        fetch=False,
    )
    conn.commit()

    # Fetch back incident ids in insertion order to link suspects/victims
    cur.execute("SELECT id, crime_type FROM incidents ORDER BY id")
    all_incidents = cur.fetchall()

    # --- Link suspects/victims to incidents ---
    ring_incident_count = 0
    link_rows_s, link_rows_v = [], []
    ring_incident_ids = []
    for inc_id, crime_type in all_incidents:
        # 8% chance this incident belongs to the deliberately injected ring
        if crime_type in ("Vehicle Theft", "Theft") and random.random() < 0.08:
            sus = random.choice(ring_suspects)
            ring_incident_count += 1
            ring_incident_ids.append(inc_id)
        else:
            sus = random.choice(suspect_ids)
        link_rows_s.append((inc_id, sus))
        n_victims = random.randint(1, 2)
        for v in random.sample(victim_ids, n_victims):
            link_rows_v.append((inc_id, v))

    execute_values(cur, "INSERT INTO incident_suspects (incident_id, suspect_id) VALUES %s", link_rows_s)
    execute_values(cur, "INSERT INTO incident_victims (incident_id, victim_id) VALUES %s", link_rows_v)

    # Overwrite MO fields on the ring's incidents so they actually share a similarity
    # signature (weapon/target/escape) — this is the real signal Phase 3's cosine
    # similarity clustering needs to recover. Without this, linking the same suspects
    # to incidents means nothing if their MO fields are still randomized independently.
    if ring_incident_ids:
        cur.execute(
            """UPDATE incidents SET weapon_or_method = %s, target_type = %s, escape_pattern = %s
               WHERE id = ANY(%s)""",
            (RING_MO["weapon_or_method"], RING_MO["target_type"], RING_MO["escape_pattern"], ring_incident_ids),
        )
    conn.commit()

    cur.close()
    conn.close()

    # --- Print the injected-pattern summary: KEEP THIS for Phase 4 validation ---
    print("=" * 70)
    print("SYNTHETIC DATA GENERATION SUMMARY — injected ground-truth patterns")
    print("=" * 70)
    print(f"Total incidents created: {incidents_created}")
    print(f"Date range: {SIM_START.date()} to {SIM_END.date()}")
    print(f"Stations: {sum(len(v) for v in DISTRICTS.values())} across {len(DISTRICTS)} districts")
    print(f"Suspects: {N_SUSPECTS} | Victims: {N_VICTIMS}")
    print("\nInjected pattern 1 — Base daily rates per crime type:")
    for k, v in BASE_RATE.items():
        print(f"   {k}: {v}")
    print("\nInjected pattern 2 — Weekend multipliers (model should detect weekend skew):")
    for k, v in WEEKEND_MULTIPLIER.items():
        print(f"   {k}: x{v}")
    print("\nInjected pattern 3 — Night-hour multipliers, 22:00-04:00 (model should detect night skew):")
    for k, v in NIGHT_MULTIPLIER.items():
        print(f"   {k}: x{v}")
    print(f"\nInjected pattern 4 — Seasonal spike in months {sorted(SEASONAL_MONTHS)} (Oct-Nov):")
    for k, v in SEASONAL_MULTIPLIER.items():
        print(f"   {k}: x{v}")
    print(f"\nInjected pattern 5 — Deliberate hotspot: '{HOTSPOT_STATION}' has x{HOTSPOT_MULTIPLIER} "
          f"rate for '{HOTSPOT_CRIME}' (model/red-zone alerting should flag this station-crime pair)")
    print(f"\nInjected pattern 6 — Recent spike (last {RECENT_SPIKE_WEEKS} weeks only): "
          f"'{RECENT_SPIKE_STATION}' has x{RECENT_SPIKE_MULTIPLIER} rate for '{RECENT_SPIKE_CRIME}' "
          f"starting {(SIM_END - timedelta(weeks=RECENT_SPIKE_WEEKS)).date()} "
          f"(this is the case the z-score red-zone alerting endpoint should catch — distinct "
          f"from the static hotspot above, which has always been elevated and won't trigger a "
          f"recency-based z-score alert)")
    print(f"\nInjected pattern 7 — Repeat-offender ring: 5 suspects (ids {ring_suspects}) share MO "
          f"{RING_MO} across {ring_incident_count} incidents spanning multiple stations "
          f"(Phase 3 cosine-similarity clustering should group these 5 together)")
    print("=" * 70)


if __name__ == "__main__":
    main()
