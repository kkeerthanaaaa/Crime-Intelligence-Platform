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

# Check the week with the highest roll4_prev4_ratio for Jayanagar (the recent-spike week)
jaya = model_df[model_df["station_name"] == "Jayanagar PS"].sort_values("week")
target_idx = jaya["roll4_prev4_ratio"].idxmax()
row_pos = model_df.index.get_loc(target_idx)

print(f"Row: {model_df.loc[target_idx, ['station_name','week','total_count','predicted']].to_dict()}")
print("\nSHAP feature contributions for this specific week's prediction:")
contribs = pd.Series(shap_values[row_pos], index=FEATURE_COLS).sort_values(key=abs, ascending=False)
print(contribs.head(8))
print(f"\nBase value (average prediction): {explainer.expected_value:.2f}")
