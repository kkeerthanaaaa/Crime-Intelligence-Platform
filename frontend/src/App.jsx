import { useEffect, useMemo, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import "./App.css";
import { api } from "./api";
import HeatmapLayer from "./components/HeatmapLayer";
import FlyToBounds from "./components/FlyToBounds";
import NetworkGraph from "./components/NetworkGraph";
import RiskDashboard from "./components/RiskDashboard";
import { densityColor, densityRadius, boundsForStations } from "./utils";

const KARNATAKA_CENTER = [14.5, 75.7];
const KARNATAKA_BOUNDS = [
  [11.5, 74.0],
  [18.5, 78.5],
];

function App() {
  const [tab, setTab] = useState("map"); // "map" | "network"

  const [districts, setDistricts] = useState([]);
  const [crimeTypes, setCrimeTypes] = useState([]);
  const [stations, setStations] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [redzones, setRedzones] = useState([]);

  const [selectedDistrict, setSelectedDistrict] = useState(null);
  const [crimeTypeFilter, setCrimeTypeFilter] = useState("");
  const [viewMode, setViewMode] = useState("density"); // "density" | "heatmap"
  const [timeOfDay, setTimeOfDay] = useState(""); // "" | "day" | "night"
  const [dayType, setDayType] = useState(""); // "" | "weekday" | "weekend"

  const [networkTopN, setNetworkTopN] = useState(12);
  const [networkMaxIncidents, setNetworkMaxIncidents] = useState(8);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Initial load: districts/crime-types for filter dropdowns, and red-zone alerts.
  useEffect(() => {
    Promise.all([api.districts(), api.redzones()])
      .then(([d, rz]) => {
        setDistricts(d.districts);
        setCrimeTypes(d.crime_types);
        setRedzones(rz.redzones);
      })
      .catch((err) => setError(err.message));
  }, []);

  // Station density stats — refetch whenever the crime-type filter changes.
  useEffect(() => {
    if (tab !== "map") return;
    setLoading(true);
    api
      .stationStats(crimeTypeFilter || undefined)
      .then((data) => {
        setStations(data.stations);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [tab, crimeTypeFilter]);

  // Incident points — only needed for heatmap mode, refetch on any relevant filter change.
  useEffect(() => {
    if (tab !== "map" || viewMode !== "heatmap") return;
    api
      .incidents({
        crimeType: crimeTypeFilter || undefined,
        timeOfDay: timeOfDay || undefined,
        dayType: dayType || undefined,
        district: selectedDistrict || undefined,
        limit: 20000,
      })
      .then((data) => setIncidents(data.incidents))
      .catch((err) => setError(err.message));
  }, [tab, viewMode, crimeTypeFilter, timeOfDay, dayType, selectedDistrict]);

  const visibleStations = useMemo(
    () => (selectedDistrict ? stations.filter((s) => s.district === selectedDistrict) : stations),
    [stations, selectedDistrict]
  );

  const countRange = useMemo(() => {
    const counts = visibleStations.map((s) => s.incident_count);
    if (counts.length === 0) return { min: 0, max: 1 };
    return { min: Math.min(...counts), max: Math.max(...counts) };
  }, [visibleStations]);

  const flyBounds = useMemo(
    () => (selectedDistrict ? boundsForStations(stations.filter((s) => s.district === selectedDistrict)) : null),
    [selectedDistrict, stations]
  );

  const redzoneStationIds = useMemo(() => new Set(redzones.map((r) => r.station_id)), [redzones]);

  if (error) return <p style={{ padding: 20, color: "red" }}>Error: {error}</p>;

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <h2>KSP Crime Intelligence</h2>

        <div className="tab-row">
          <button className={tab === "map" ? "active" : ""} onClick={() => setTab("map")}>
            🗺 Map
          </button>
          <button className={tab === "network" ? "active" : ""} onClick={() => setTab("network")}>
            🕸 Network
          </button>
          <button className={tab === "risk" ? "active" : ""} onClick={() => setTab("risk")}>
            📊 Risk
          </button>
        </div>

        {tab === "map" && (
          <>
            <section>
              <h3>District drill-down</h3>
              <ul className="district-list">
                <li
                  className={selectedDistrict === null ? "active" : ""}
                  onClick={() => setSelectedDistrict(null)}
                >
                  All districts
                </li>
                {districts.map((d) => (
                  <li
                    key={d}
                    className={selectedDistrict === d ? "active" : ""}
                    onClick={() => setSelectedDistrict(d)}
                  >
                    {d}
                  </li>
                ))}
              </ul>
            </section>

            <section>
              <h3>Crime type</h3>
              <select value={crimeTypeFilter} onChange={(e) => setCrimeTypeFilter(e.target.value)}>
                <option value="">All crime types</option>
                {crimeTypes.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </section>

            <section>
              <h3>View mode</h3>
              <div className="toggle-row">
                <button className={viewMode === "density" ? "active" : ""} onClick={() => setViewMode("density")}>
                  Density
                </button>
                <button className={viewMode === "heatmap" ? "active" : ""} onClick={() => setViewMode("heatmap")}>
                  Heatmap
                </button>
              </div>
            </section>

            {viewMode === "heatmap" && (
              <section>
                <h3>Heatmap filters</h3>
                <div className="toggle-row">
                  <button className={timeOfDay === "" ? "active" : ""} onClick={() => setTimeOfDay("")}>
                    All hours
                  </button>
                  <button className={timeOfDay === "day" ? "active" : ""} onClick={() => setTimeOfDay("day")}>
                    Day
                  </button>
                  <button className={timeOfDay === "night" ? "active" : ""} onClick={() => setTimeOfDay("night")}>
                    Night
                  </button>
                </div>
                <div className="toggle-row">
                  <button className={dayType === "" ? "active" : ""} onClick={() => setDayType("")}>
                    All days
                  </button>
                  <button className={dayType === "weekday" ? "active" : ""} onClick={() => setDayType("weekday")}>
                    Weekday
                  </button>
                  <button className={dayType === "weekend" ? "active" : ""} onClick={() => setDayType("weekend")}>
                    Weekend
                  </button>
                </div>
              </section>
            )}

            <section>
              <h3>🔴 Red-zone alerts ({redzones.length})</h3>
              {redzones.length === 0 && <p className="muted">No stations currently exceed baseline.</p>}
              <ul className="redzone-list">
                {redzones.map((r) => (
                  <li key={`${r.station_id}-${r.crime_type}`} className="redzone-item">
                    <strong>{r.station_name}</strong> — {r.crime_type}
                    <br />
                    <span className="muted">
                      {r.current_avg_weekly_count}/wk vs baseline {r.baseline_mean}/wk (z={r.z_score})
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          </>
        )}

        {tab === "network" && (
          <section>
            <h3>Network settings</h3>
            <label className="field-label">
              Top N most active suspects: {networkTopN}
              <input
                type="range"
                min="5"
                max="30"
                value={networkTopN}
                onChange={(e) => setNetworkTopN(Number(e.target.value))}
              />
            </label>
            <label className="field-label">
              Max sampled incidents/suspect: {networkMaxIncidents}
              <input
                type="range"
                min="3"
                max="20"
                value={networkMaxIncidents}
                onChange={(e) => setNetworkMaxIncidents(Number(e.target.value))}
              />
            </label>
            <p className="muted">
              Click any node in the graph to see details. Suspects with matching colors
              (other than the default red) share a detected MO pattern.
            </p>
          </section>
        )}
      </aside>

      {tab === "map" && (
        <main className="map-area">
          {loading && <div className="loading-banner">Loading...</div>}
          <MapContainer center={KARNATAKA_CENTER} zoom={7} maxBounds={KARNATAKA_BOUNDS} style={{ height: "100%", width: "100%" }}>
            <TileLayer
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              attribution="&copy; OpenStreetMap contributors"
            />
            <FlyToBounds bounds={flyBounds} />

            {viewMode === "density" &&
              visibleStations.map((s) => (
                <CircleMarker
                  key={s.id}
                  center={[s.lat, s.long]}
                  radius={densityRadius(s.incident_count, countRange.min, countRange.max)}
                  pathOptions={{
                    color: redzoneStationIds.has(s.id) ? "#000" : "#555",
                    weight: redzoneStationIds.has(s.id) ? 3 : 1,
                    fillColor: densityColor(s.incident_count, countRange.min, countRange.max),
                    fillOpacity: 0.75,
                    className: redzoneStationIds.has(s.id) ? "pulse-marker" : "",
                  }}
                >
                  <Popup>
                    <strong>{s.name}</strong> ({s.district})
                    <br />
                    {s.incident_count} incidents{crimeTypeFilter ? ` (${crimeTypeFilter})` : ""}
                    {redzoneStationIds.has(s.id) && (
                      <>
                        <br />
                        <span style={{ color: "red" }}>⚠ Red-zone alert active</span>
                      </>
                    )}
                  </Popup>
                </CircleMarker>
              ))}

            {viewMode === "heatmap" && <HeatmapLayer points={incidents} />}
          </MapContainer>
          <div className="legend">
            Note: choropleth colors station catchment areas by incident density — we don't have
            real KSP district administrative boundary shapefiles, so this uses station
            jurisdiction circles as an honest approximation, not true district polygons.
          </div>
        </main>
      )}

      {tab === "network" && (
        <main className="map-area">
          <NetworkGraph topN={networkTopN} maxIncidentsPerSuspect={networkMaxIncidents} district={selectedDistrict} />
        </main>
      )}

      {tab === "risk" && (
        <main className="map-area">
          <RiskDashboard />
        </main>
      )}
    </div>
  );
}

export default App;
