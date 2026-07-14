"""
Groups raw SHAP feature contributions into human-readable categories and generates
a plain-English explanation sentence. Shared between the validation notebook and
the FastAPI risk-scoring endpoint so the explanation logic is defined once.
"""

FEATURE_GROUPS = {
    "recent_trend": ["lag1_total", "roll4_total", "roll8_total", "roll4_prev4_ratio"],
    "time_of_day_pattern": ["lag_night_share"],
    "weekly_pattern": ["lag_weekend_share"],
    "seasonal_factor": ["is_festival_season"],
    "crime_type_mix": [
        "mix_Assault", "mix_Burglary", "mix_Chain Snatching", "mix_Cybercrime",
        "mix_Robbery", "mix_Theft", "mix_Vehicle Theft",
    ],
}

GROUP_LABELS = {
    "recent_trend": "recent incident trend",
    "time_of_day_pattern": "time-of-day pattern",
    "weekly_pattern": "weekday/weekend pattern",
    "seasonal_factor": "seasonal factor",
    "crime_type_mix": "crime-type mix",
}


def aggregate_shap_to_groups(shap_row, feature_cols):
    """shap_row: array of per-feature SHAP values for one prediction.
    Returns list of {group, label, pct, direction} sorted by |contribution| desc.
    """
    contrib_by_feature = dict(zip(feature_cols, shap_row))
    group_totals = {}
    for group, cols in FEATURE_GROUPS.items():
        group_totals[group] = sum(contrib_by_feature.get(c, 0.0) for c in cols)

    total_abs = sum(abs(v) for v in group_totals.values())
    if total_abs == 0:
        total_abs = 1e-9  # avoid div by zero on a degenerate all-zero row

    result = []
    for group, val in group_totals.items():
        result.append({
            "group": group,
            "label": GROUP_LABELS[group],
            "pct": round(100 * float(abs(val)) / float(total_abs), 1),
            "direction": "increasing" if val > 0 else "decreasing",
            "raw_contribution": round(float(val), 3),
        })
    result.sort(key=lambda r: r["pct"], reverse=True)
    return result


def generate_explanation_sentence(station_name, predicted_risk, base_value, grouped):
    """Builds the plain-English sentence, e.g.:
    'Station X shows elevated risk (predicted 31 incidents/week vs a typical 26)
    driven primarily by crime-type mix (42%) and recent incident trend (28%).'
    """
    increasing = [g for g in grouped if g["direction"] == "increasing"]
    top_factors = increasing[:2] if increasing else grouped[:2]

    if predicted_risk > base_value * 1.1:
        risk_word = "elevated"
    elif predicted_risk < base_value * 0.9:
        risk_word = "below-average"
    else:
        risk_word = "typical"

    factor_text = " and ".join(f"{g['label']} ({g['pct']}%)" for g in top_factors)
    return (
        f"{station_name} shows {risk_word} predicted risk "
        f"({predicted_risk:.0f} incidents/week vs a station-average baseline of {base_value:.0f}), "
        f"driven primarily by {factor_text}."
    )
