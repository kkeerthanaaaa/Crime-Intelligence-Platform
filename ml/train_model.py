"""
Train an explainable weekly risk-prediction model per station.

TARGET: total_count in week W (what we're predicting)
FEATURES: built ONLY from weeks < W (rolling lags) — this is a genuine forecast
setup, not just fitting current-week features to current-week counts, which would
be trivially "accurate" but useless (you can't know this week's crime-type mix
before the week happens).
"""
import pandas as pd
import numpy as np
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, r2_score

weekly = pd.read_pickle("/home/claude/ksp-platform/ml/weekly_station_data.pkl")
weekly = weekly.sort_values(["station_id", "week"]).reset_index(drop=True)

CRIME_TYPES = ['Assault', 'Burglary', 'Chain Snatching', 'Cybercrime', 'Robbery', 'Theft', 'Vehicle Theft']

FEATURE_COLS = []

def add_lag_features(g):
    g = g.copy()
    # Recent trend: rolling mean of total_count over past 1, 4, 8 weeks (shifted so
    # week W's features only see weeks < W)
    g["lag1_total"] = g["total_count"].shift(1)
    g["roll4_total"] = g["total_count"].shift(1).rolling(4, min_periods=1).mean()
    g["roll8_total"] = g["total_count"].shift(1).rolling(8, min_periods=1).mean()
    # Recent trend direction: last 4 weeks vs prior 4 weeks (captures emerging spikes,
    # same idea as the red-zone alerting in Phase 2, now as a model feature)
    g["roll4_prev4_ratio"] = g["roll4_total"] / g["total_count"].shift(5).rolling(4, min_periods=1).mean().replace(0, np.nan)
    # Time-of-day / weekend pattern, lagged (this station's historical night/weekend share)
    g["lag_night_share"] = g["night_share"].shift(1).rolling(8, min_periods=1).mean()
    g["lag_weekend_share"] = g["weekend_share"].shift(1).rolling(8, min_periods=1).mean()
    # Crime-type mix, lagged (proportions over trailing 8 weeks)
    for ct in CRIME_TYPES:
        col = f"mix_{ct}"
        g[col] = (g[ct].shift(1).rolling(8, min_periods=1).sum() /
                  g["total_count"].shift(1).rolling(8, min_periods=1).sum().replace(0, np.nan))
    return g

weekly = weekly.groupby("station_id", group_keys=False).apply(add_lag_features, include_groups=False).join(weekly[["station_id"]])
weekly["month"] = pd.to_datetime(weekly["week"]).dt.month
weekly["is_festival_season"] = weekly["month"].isin([10, 11]).astype(int)

FEATURE_COLS = ["lag1_total", "roll4_total", "roll8_total", "roll4_prev4_ratio",
                 "lag_night_share", "lag_weekend_share", "is_festival_season"] + [f"mix_{ct}" for ct in CRIME_TYPES]

model_df = weekly.dropna(subset=FEATURE_COLS + ["total_count"]).reset_index(drop=True)
print(f"Modeling rows after dropping warm-up period (need history for lags): {len(model_df)} / {len(weekly)}")

# TIME-BASED split (not random) — train on earlier weeks, test on later weeks.
# Random splitting would leak future information into training, which is invalid
# for a forecasting problem and would make test performance look better than it
# actually is in production.
split_week = model_df["week"].quantile(0.75, interpolation="nearest")
train = model_df[model_df["week"] < split_week]
test = model_df[model_df["week"] >= split_week]
print(f"Train: {len(train)} rows (weeks < {pd.Timestamp(split_week).date()})")
print(f"Test:  {len(test)} rows (weeks >= {pd.Timestamp(split_week).date()})")

X_train, y_train = train[FEATURE_COLS], train["total_count"]
X_test, y_test = test[FEATURE_COLS], test["total_count"]

model = XGBRegressor(n_estimators=200, max_depth=4, learning_rate=0.05, random_state=42)
model.fit(X_train, y_train)

pred_train = model.predict(X_train)
pred_test = model.predict(X_test)

print("\n=== Model performance ===")
print(f"Train MAE: {mean_absolute_error(y_train, pred_train):.2f}, R²: {r2_score(y_train, pred_train):.3f}")
print(f"Test  MAE: {mean_absolute_error(y_test, pred_test):.2f}, R²: {r2_score(y_test, pred_test):.3f}")

# Baseline comparison: naive "predict last week's count" — the model needs to beat this
naive_pred = test["lag1_total"]
print(f"Naive baseline (predict lag1) Test MAE: {mean_absolute_error(y_test, naive_pred):.2f}")

model.save_model("/home/claude/ksp-platform/ml/risk_model.json")
model_df.to_pickle("/home/claude/ksp-platform/ml/model_df.pkl")
import json
with open("/home/claude/ksp-platform/ml/feature_cols.json", "w") as f:
    json.dump(FEATURE_COLS, f)
print("\nSaved model, model_df, feature_cols.")
