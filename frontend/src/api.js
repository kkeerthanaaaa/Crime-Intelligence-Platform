const API_BASE = "http://localhost:8000";

async function getJSON(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`API ${path} returned ${res.status}`);
  return res.json();
}

export const api = {
  districts: () => getJSON("/api/districts"),
  stationStats: (crimeType) =>
    getJSON(`/api/station-stats${crimeType ? `?crime_type=${encodeURIComponent(crimeType)}` : ""}`),
  incidents: ({ crimeType, timeOfDay, dayType, district, limit = 5000 } = {}) => {
    const params = new URLSearchParams();
    if (crimeType) params.set("crime_type", crimeType);
    if (timeOfDay) params.set("time_of_day", timeOfDay);
    if (dayType) params.set("day_type", dayType);
    if (district) params.set("district", district);
    params.set("limit", limit);
    return getJSON(`/api/incidents?${params.toString()}`);
  },
  redzones: () => getJSON("/api/redzones"),
  stations: () => getJSON("/api/stations"),
};

export default API_BASE;
