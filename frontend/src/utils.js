// Color scale for choropleth-style station density circles.
// Buckets are computed from the actual min/max in the current filtered dataset,
// so colors stay meaningful even as filters change the range.
const COLORS = ["#fee5d9", "#fcae91", "#fb6a4a", "#de2d26", "#a50f15"];

export function densityColor(count, min, max) {
  if (max === min) return COLORS[2];
  const ratio = (count - min) / (max - min);
  const idx = Math.min(COLORS.length - 1, Math.floor(ratio * COLORS.length));
  return COLORS[idx];
}

export function densityRadius(count, min, max) {
  if (max === min) return 14;
  const ratio = (count - min) / (max - min);
  return 10 + ratio * 22; // 10px to 32px
}

export function boundsForStations(stations) {
  if (!stations || stations.length === 0) return null;
  const lats = stations.map((s) => s.lat);
  const longs = stations.map((s) => s.long);
  return [
    [Math.min(...lats) - 0.05, Math.min(...longs) - 0.05],
    [Math.max(...lats) + 0.05, Math.max(...longs) + 0.05],
  ];
}
