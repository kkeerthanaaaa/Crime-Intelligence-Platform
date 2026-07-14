import pandas as pd
import numpy as np
from xgboost import XGBRegressor
import json

model_df = pd.read_pickle("/home/claude/ksp-platform/ml/model_df.pkl")
with open("/home/claude/ksp-platform/ml/feature_cols.json") as f:
    FEATURE_COLS = json.load(f)

model = XGBRegressor()
model.load_model("/home/claude/ksp-platform/ml/risk_model.json")

model_df["predicted"] = model.predict(model_df[FEATURE_COLS])

print("=== VALIDATION 1: Feature importance — does the model actually rely on the")
print("    features we'd expect (recent trend, night/weekend share, crime mix)? ===")
importances = pd.Series(model.feature_importances_, index=FEATURE_COLS).sort_values(ascending=False)
print(importances.head(10))

print("\n=== VALIDATION 2: Whitefield PS (injected static hotspot for Vehicle Theft) —")
print("    does the model predict elevated risk there vs other stations? ===")
station_avg_pred = model_df.groupby("station_name")["predicted"].mean().sort_values(ascending=False)
print(station_avg_pred)

print("\n=== VALIDATION 3: Jayanagar PS Robbery recent spike (injected in the last 4")
print("    weeks of the dataset, which falls in the TEST period) — does predicted")
print("    risk rise for Jayanagar's final weeks vs its own earlier weeks? ===")
jaya = model_df[model_df["station_name"] == "Jayanagar PS"].sort_values("week")
print(jaya[["week", "total_count", "predicted", "roll4_prev4_ratio"]].tail(8).to_string(index=False))
