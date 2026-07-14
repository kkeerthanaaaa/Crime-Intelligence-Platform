import pandas as pd
import numpy as np
from xgboost import XGBRegressor
import shap
import json

model_df = pd.read_pickle("/home/claude/ksp-platform/ml/model_df.pkl")
with open("/home/claude/ksp-platform/ml/feature_cols.json") as f:
    FEATURE_COLS = json.load(f)

model = XGBRegressor()
model.load_model("/home/claude/ksp-platform/ml/risk_model.json")
model_df["predicted"] = model.predict(model_df[FEATURE_COLS])

explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(model_df[FEATURE_COLS])

# Target the ACTUAL injected spike weeks for Jayanagar (last few weeks of Dec 2025,
# which is when the recent-spike pattern was injected in generate_data.py)
jaya = model_df[model_df["station_name"] == "Jayanagar PS"].sort_values("week")
target_weeks = jaya[jaya["week"] >= "2025-12-01"]
print("Target weeks (during injected Robbery spike):")
print(target_weeks[["week", "total_count", "predicted", "roll4_prev4_ratio"]].to_string(index=False))

for idx in target_weeks.index:
    row_pos = model_df.index.get_loc(idx)
    print(f"\n--- SHAP for week {model_df.loc[idx,'week'].date()} (predicted={model_df.loc[idx,'predicted']:.1f}) ---")
    contribs = pd.Series(shap_values[row_pos], index=FEATURE_COLS).sort_values(key=abs, ascending=False)
    print(contribs.head(5))
