"""
Compares observed/model-predicted patterns against the known ground-truth patterns
deliberately injected in generate_data.py (imported directly from there so the two
can never drift out of sync).

HONESTY NOTE ON METHODOLOGY: this file deliberately keeps two DIFFERENT kinds of
recovery separate rather than blurring them together:

- "data_level" recovery: computed directly from the incidents table via SQL. This
  validates that the injected pattern is actually present in the data (and that
  Phase 1's generator worked correctly) — it does NOT involve the trained model at
  all.
- "model_level" recovery: computed FROM the trained risk model, via counterfactual
  predictions (e.g. predicting with is_festival_season=1 vs 0, holding other features
  at their mean) or via SHAP attribution. This validates that the MODEL learned to
  rely on the right signal.

Why the split matters: our risk model predicts TOTAL station-week volume across all
7 crime types, using station-level night/weekend shares and crime-type MIX as
features — it does not learn a clean, isolated "Burglary is 2.2x more common at
night" coefficient the way a per-crime-type model would. Claiming the model
"recovered" a per-crime-type night/day multiplier it was never architecturally able
to isolate would be overclaiming. Presenting data-level recovery honestly as
data-level (not model-level) keeps the claims accurate.
"""

import numpy as np
import pandas as pd

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from generate_data import (
    WEEKEND_MULTIPLIER, NIGHT_MULTIPLIER, SEASONAL_MULTIPLIER, SEASONAL_MONTHS,
    HOTSPOT_STATION, HOTSPOT_CRIME, HOTSPOT_MULTIPLIER,
    RECENT_SPIKE_STATION, RECENT_SPIKE_CRIME, RECENT_SPIKE_MULTIPLIER, RECENT_SPIKE_WEEKS,
)


def compute_data_level_recovery(conn):
    """Directly from the incidents table: observed night/day and weekend/weekday
    ratios per crime type, compared to the injected ground-truth multipliers.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT crime_type,
                   EXTRACT(HOUR FROM "timestamp") AS hour,
                   EXTRACT(DOW FROM "timestamp") AS dow
            FROM incidents
        """)
        rows = cur.fetchall()

    df = pd.DataFrame(rows)
    df["is_night"] = ((df["hour"] >= 22) | (df["hour"] < 5))
    df["is_weekend"] = df["dow"].isin([0, 6])

    results = []
    for crime_type, injected_mult in NIGHT_MULTIPLIER.items():
        night_count = (df["crime_type"].eq(crime_type) & df["is_night"]).sum()
        day_count = (df["crime_type"].eq(crime_type) & ~df["is_night"]).sum()
        # Normalize by clock-hours (7 night hours vs 17 day hours) for a fair rate comparison
        night_rate = night_count / 7
        day_rate = day_count / 17
        observed_ratio = round(float(night_rate / day_rate), 2) if day_rate > 0 else None
        results.append({
            "pattern": f"{crime_type}: night vs day rate",
            "injected_multiplier": injected_mult,
            "observed_multiplier": observed_ratio,
            "type": "night_day",
        })

    for crime_type, injected_mult in WEEKEND_MULTIPLIER.items():
        wknd_count = (df["crime_type"].eq(crime_type) & df["is_weekend"]).sum()
        wkday_count = (df["crime_type"].eq(crime_type) & ~df["is_weekend"]).sum()
        wknd_rate = wknd_count / 2
        wkday_rate = wkday_count / 5
        observed_ratio = round(float(wknd_rate / wkday_rate), 2) if wkday_rate > 0 else None
        results.append({
            "pattern": f"{crime_type}: weekend vs weekday rate",
            "injected_multiplier": injected_mult,
            "observed_multiplier": observed_ratio,
            "type": "weekend_weekday",
        })

    return results


def compute_model_level_recovery(model, model_df, feature_cols):
    """From the trained model: counterfactual predictions and SHAP-based checks for
    the patterns this model's architecture can actually express (seasonal factor as
    a direct feature; hotspot and recent-spike as station-average / SHAP checks,
    already computed elsewhere and summarized here for the dashboard).
    """
    results = []

    # Seasonal factor: direct counterfactual — same row, flip is_festival_season
    baseline_row = model_df[feature_cols].mean().to_frame().T
    row_on = baseline_row.copy()
    row_on["is_festival_season"] = 1
    row_off = baseline_row.copy()
    row_off["is_festival_season"] = 0
    pred_on = float(model.predict(row_on)[0])
    pred_off = float(model.predict(row_off)[0])
    model_seasonal_ratio = round(pred_on / pred_off, 2) if pred_off > 0 else None
    injected_seasonal_avg = round(float(np.mean(list(SEASONAL_MULTIPLIER.values()))), 2)
    results.append({
        "pattern": "Festival season (Oct-Nov) effect on predicted station volume",
        "injected_multiplier": injected_seasonal_avg,
        "observed_multiplier": model_seasonal_ratio,
        "type": "model_counterfactual",
        "note": "Model predicts TOTAL station volume; injected value shown is the average "
                "of the per-crime-type seasonal multipliers, since the model doesn't isolate them individually.",
    })

    # Hotspot: station-average predicted risk ratio (already validated in the notebook)
    model_df = model_df.copy()
    model_df["predicted"] = model.predict(model_df[feature_cols])
    station_avg = model_df.groupby("station_name")["predicted"].mean()
    hotspot_avg = station_avg.get(HOTSPOT_STATION, None)
    other_avg = station_avg.drop(HOTSPOT_STATION, errors="ignore").mean()
    model_hotspot_ratio = round(float(hotspot_avg) / float(other_avg), 2) if hotspot_avg and other_avg else None
    results.append({
        "pattern": f"{HOTSPOT_STATION} station-average risk vs other stations",
        "injected_multiplier": HOTSPOT_MULTIPLIER,
        "observed_multiplier": model_hotspot_ratio,
        "type": "model_station_average",
        "note": f"Injected value is the {HOTSPOT_CRIME}-specific rate multiplier; observed value "
                f"is the model's predicted TOTAL volume ratio (diluted across all crime types), "
                f"so exact match isn't expected — direction and magnitude are what matter here.",
    })

    return results
