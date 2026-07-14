"""
Feature engineering for station-week risk prediction.
For each (station, week), predict NEXT week's total incident count from features
computed ONLY from prior weeks — this is a genuine forecasting setup (no leakage).
"""
import psycopg2
import psycopg2.extras
import pandas as pd
import numpy as np

conn = psycopg2.connect(dbname="ksp_crime", user="postgres", password="postgres", host="localhost", cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()
cur.execute("""
    SELECT s.id AS station_id, s.name AS station_name, s.district,
           i.crime_type, i."timestamp"
    FROM incidents i JOIN stations s ON s.id = i.station_id
""")
rows = cur.fetchall()
conn.close()

df = pd.DataFrame(rows)
df["timestamp"] = pd.to_datetime(df["timestamp"])
df["week"] = df["timestamp"].dt.to_period("W").dt.start_time
df["hour"] = df["timestamp"].dt.hour
df["is_night"] = ((df["hour"] >= 22) | (df["hour"] < 5)).astype(int)
df["dow"] = df["timestamp"].dt.dayofweek
df["is_weekend"] = (df["dow"] >= 5).astype(int)
df["month"] = df["timestamp"].dt.month

CRIME_TYPES = sorted(df["crime_type"].unique())
stations = df[["station_id", "station_name", "district"]].drop_duplicates()

all_weeks = sorted(df["week"].unique())
print(f"Total weeks in dataset: {len(all_weeks)} ({all_weeks[0].date()} to {all_weeks[-1].date()})")
print(f"Stations: {len(stations)}, Crime types: {CRIME_TYPES}")

# Build station-week incident counts (total + per crime type)
weekly = df.groupby(["station_id", "week"]).size().rename("total_count").reset_index()
crime_pivot = df.groupby(["station_id", "week", "crime_type"]).size().unstack(fill_value=0).reset_index()
weekly = weekly.merge(crime_pivot, on=["station_id", "week"], how="left")

night_pivot = df.groupby(["station_id", "week"])["is_night"].mean().rename("night_share").reset_index()
weekend_pivot = df.groupby(["station_id", "week"])["is_weekend"].mean().rename("weekend_share").reset_index()
weekly = weekly.merge(night_pivot, on=["station_id", "week"], how="left")
weekly = weekly.merge(weekend_pivot, on=["station_id", "week"], how="left")

weekly = weekly.sort_values(["station_id", "week"]).reset_index(drop=True)

# Build a full station x week grid (fill missing weeks with 0s) so rolling windows are correct
full_grid = pd.MultiIndex.from_product([stations["station_id"], all_weeks], names=["station_id", "week"]).to_frame(index=False)
weekly = full_grid.merge(weekly, on=["station_id", "week"], how="left").fillna(0)
weekly = weekly.merge(stations, on="station_id", how="left")
weekly = weekly.sort_values(["station_id", "week"]).reset_index(drop=True)

weekly.to_pickle("/home/claude/ksp-platform/ml/weekly_station_data.pkl")
print("\nSaved weekly_station_data.pkl, shape:", weekly.shape)
print(weekly.head(10))
