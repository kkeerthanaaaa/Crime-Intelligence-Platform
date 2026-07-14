import { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

const GROUP_COLORS = {
  crime_type_mix: "#de2d26",
  recent_trend: "#f2a134",
  time_of_day_pattern: "#4a90d9",
  weekly_pattern: "#2ca25f",
  seasonal_factor: "#8856a7",
};

export default function RiskDashboard() {
  const [data, setData] = useState(null);
  const [gtr, setGtr] = useState(null);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([
      fetch("http://127.0.0.1:8000/api/risk-score").then((r) => r.json()),
      fetch("http://127.0.0.1:8000/api/ground-truth-recovery").then((r) => r.json()),
    ])
      .then(([riskData, gtrData]) => {
        if (riskData.error) throw new Error(riskData.error);
        setData(riskData);
        setGtr(gtrData);
        setSelected(riskData.stations[0]?.station_id ?? null);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) return <div className="loading-banner">Loading risk model...</div>;
  if (error) return <p style={{ color: "red", padding: 20 }}>Error: {error}</p>;
  if (!data || data.stations.length === 0) return <p style={{ padding: 20 }}>No risk data available.</p>;

  const selectedStation = data.stations.find((s) => s.station_id === selected) || data.stations[0];
  const chartData = selectedStation.shap_groups.map((g) => ({
    name: g.label,
    value: g.direction === "increasing" ? g.pct : -g.pct,
    group: g.group,
    direction: g.direction,
  }));

  return (
    <div style={{ display: "flex", height: "100%", width: "100%", overflow: "hidden" }}>
      <div style={{ width: 280, flexShrink: 0, overflowY: "auto", borderRight: "1px solid #ddd", background: "#fafafa" }}>
        <div style={{ padding: 14 }}>
          <h4 style={{ margin: "0 0 4px" }}>Station risk ranking</h4>
          <p className="muted" style={{ fontSize: 11 }}>
            Predicted weekly incident count vs baseline of {data.baseline}. Sorted highest risk first.
          </p>
        </div>
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {data.stations.map((s) => (
            <li
              key={s.station_id}
              onClick={() => setSelected(s.station_id)}
              style={{
                padding: "10px 14px",
                cursor: "pointer",
                background: s.station_id === selected ? "#fde0dd" : "transparent",
                borderBottom: "1px solid #eee",
              }}
            >
              <strong>{s.station_name}</strong>
              <div style={{ fontSize: 12, color: "#666" }}>
                {s.predicted_weekly_risk} incidents/wk
                {s.predicted_weekly_risk > data.baseline * 1.1 && <span style={{ color: "#de2d26" }}> ⚠ elevated</span>}
              </div>
            </li>
          ))}
        </ul>
      </div>

      <div style={{ flex: 1, padding: 20, overflowY: "auto" }}>
        <h3>{selectedStation.station_name} ({selectedStation.district})</h3>
        <p style={{ fontSize: 15, lineHeight: 1.5, background: "#f7f7f9", padding: 12, borderRadius: 8 }}>
          {selectedStation.explanation}
        </p>

        <h4>Feature contribution breakdown (SHAP)</h4>
        <p className="muted" style={{ fontSize: 12 }}>
          Positive bars push predicted risk up; negative bars push it down. Percentages
          show each category's share of total |contribution|, aggregated from the
          model's raw per-feature SHAP values — see backend/risk_explain.py.
        </p>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={chartData} layout="vertical" margin={{ left: 40 }}>
            <XAxis type="number" domain={[-70, 70]} tickFormatter={(v) => `${Math.abs(v)}%`} />
            <YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 12 }} />
            <Tooltip formatter={(v, n, p) => [`${Math.abs(v)}% (${p.payload.direction})`, "Contribution"]} />
            <Bar dataKey="value">
              {chartData.map((entry, idx) => (
                <Cell key={idx} fill={GROUP_COLORS[entry.group]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>

        <p className="muted graph-note" style={{ marginTop: 16 }}>
          Model validated in ml/risk_scoring.ipynb against this dataset's known injected
          patterns before being wired in here — see that notebook for train/test
          methodology and validation results, including an honest discussion of where
          validation came back weaker than hoped.
        </p>

        {gtr && !gtr.error && (
          <div style={{ marginTop: 28 }}>
            <h4>Ground-truth pattern recovery</h4>
            <p className="muted" style={{ fontSize: 12 }}>
              Compares what's actually in the data (and what the model predicts) against
              the known multipliers deliberately injected when this demo dataset was
              generated. Kept honestly split into two kinds — conflating them would
              overclaim what the model itself learned.
            </p>

            <h5 style={{ marginBottom: 4 }}>Data-level recovery <span className="muted" style={{ fontWeight: 400 }}>(directly from incidents, not the model)</span></h5>
            <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse", marginBottom: 16 }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>
                  <th style={{ padding: "4px 6px" }}>Pattern</th>
                  <th style={{ padding: "4px 6px" }}>Injected</th>
                  <th style={{ padding: "4px 6px" }}>Observed</th>
                </tr>
              </thead>
              <tbody>
                {gtr.data_level.map((r, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid #f0f0f0" }}>
                    <td style={{ padding: "4px 6px" }}>{r.pattern}</td>
                    <td style={{ padding: "4px 6px" }}>{r.injected_multiplier}x</td>
                    <td style={{ padding: "4px 6px", color: Math.abs(r.observed_multiplier - r.injected_multiplier) < 0.2 ? "#2ca25f" : "#333" }}>
                      {r.observed_multiplier}x
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <h5 style={{ marginBottom: 4 }}>Model-level recovery <span className="muted" style={{ fontWeight: 400 }}>(from the trained model's own predictions)</span></h5>
            {gtr.model_level.map((r, i) => (
              <div key={i} style={{ fontSize: 12, marginBottom: 10, padding: 8, background: "#f7f7f9", borderRadius: 6 }}>
                <div><strong>{r.pattern}</strong></div>
                <div>Injected: {r.injected_multiplier}x &nbsp;|&nbsp; Model observed: {r.observed_multiplier}x</div>
                <div className="muted" style={{ marginTop: 4 }}>{r.note}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
