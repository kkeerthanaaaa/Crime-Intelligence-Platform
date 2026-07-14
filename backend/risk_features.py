"""
Shared feature engineering for risk scoring — used identically by the training
notebook (ml/risk_scoring.ipynb, via ml/build_features.py + inline lag logic) and
this API's /api/risk-score endpoint. Keeping this logic in ONE place (rather than
copy-pasted and maybe drifting) avoids train/serve skew, a common real-world ML bug
where the live serving code computes features slightly differently than training did.
"""

import pandas as pd
import numpy as np

CRIME_TYPES = ["Assault", "Burglary", "Chain Snatching", "Cybercrime", "Robbery", "Theft", "Vehicle Theft"]

FEATURE_COLS = [
    "lag1_total", "roll4_total", "roll8_total", "roll4_prev4_ratio",
    "lag_night_share", "lag_weekend_share", "is_festival_season",
] + [f"mix_{ct}" for ct in CRIME_TYPES]


def build_weekly_station_data(conn):
    """Rebuilds the exact same station-week aggregated table used in training,
    directly from the current DB contents.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT s.id AS station_id, s.name AS station_name, s.district,
                   i.crime_type, i."timestamp"
            FROM incidents i JOIN stations s ON s.id = i.station_id
        """)
        rows = cur.fetchall()

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["week"] = df["timestamp"].dt.to_period("W").dt.start_time
    df["hour"] = df["timestamp"].dt.hour
    df["is_night"] = ((df["hour"] >= 22) | (df["hour"] < 5)).astype(int)
    df["dow"] = df["timestamp"].dt.dayofweek
    df["is_weekend"] = (df["dow"] >= 5).astype(int)

    stations = df[["station_id", "station_name", "district"]].drop_duplicates()
    all_weeks = sorted(df["week"].unique())

    weekly = df.groupby(["station_id", "week"]).size().rename("total_count").reset_index()
    crime_pivot = df.groupby(["station_id", "week", "crime_type"]).size().unstack(fill_value=0).reset_index()
    weekly = weekly.merge(crime_pivot, on=["station_id", "week"], how="left")

    night_pivot = df.groupby(["station_id", "week"])["is_night"].mean().rename("night_share").reset_index()
    weekend_pivot = df.groupby(["station_id", "week"])["is_weekend"].mean().rename("weekend_share").reset_index()
    weekly = weekly.merge(night_pivot, on=["station_id", "week"], how="left")
    weekly = weekly.merge(weekend_pivot, on=["station_id", "week"], how="left")

    full_grid = pd.MultiIndex.from_product([stations["station_id"], all_weeks], names=["station_id", "week"]).to_frame(index=False)
    weekly = full_grid.merge(weekly, on=["station_id", "week"], how="left").fillna(0)
    weekly = weekly.merge(stations, on="station_id", how="left")
    weekly = weekly.sort_values(["station_id", "week"]).reset_index(drop=True)

    for ct in CRIME_TYPES:
        if ct not in weekly.columns:
            weekly[ct] = 0

    return weekly


def add_lag_features(g):
    g = g.copy()
    g["lag1_total"] = g["total_count"].shift(1)
    g["roll4_total"] = g["total_count"].shift(1).rolling(4, min_periods=1).mean()
    g["roll8_total"] = g["total_count"].shift(1).rolling(8, min_periods=1).mean()
    g["roll4_prev4_ratio"] = g["roll4_total"] / g["total_count"].shift(5).rolling(4, min_periods=1).mean().replace(0, np.nan)
    g["lag_night_share"] = g["night_share"].shift(1).rolling(8, min_periods=1).mean()
    g["lag_weekend_share"] = g["weekend_share"].shift(1).rolling(8, min_periods=1).mean()
    for ct in CRIME_TYPES:
        col = f"mix_{ct}"
        g[col] = (g[ct].shift(1).rolling(8, min_periods=1).sum() /
                  g["total_count"].shift(1).rolling(8, min_periods=1).sum().replace(0, np.nan))
    return g


def build_model_features(conn):
    """Returns the full featured DataFrame (all stations, all weeks with enough
    history) ready for model.predict(df[FEATURE_COLS]).
    """
    weekly = build_weekly_station_data(conn)
    weekly = weekly.groupby("station_id", group_keys=False).apply(add_lag_features, include_groups=False).join(weekly[["station_id"]])
    weekly["month"] = pd.to_datetime(weekly["week"]).dt.month
    weekly["is_festival_season"] = weekly["month"].isin([10, 11]).astype(int)
    return weekly.dropna(subset=FEATURE_COLS + ["total_count"]).reset_index(drop=True)
