import { useEffect, useMemo, useRef, useState } from "react";
import { ForceGraph2D } from "react-force-graph";
import { api } from "../api";

const NODE_COLORS = {
  station: "#4a90d9",
  victim: "#888888",
};
// Suspect color depends on MO cluster — cluster 0 (the large "no strong pattern"
// group) stays neutral; other clusters get distinct colors so a shared-MO group
// visually stands out immediately.
const CLUSTER_PALETTE = ["#de2d26", "#f2a134", "#2ca25f", "#8856a7", "#c51b8a"];

function suspectColor(node) {
  if (node.cluster_id === undefined || node.cluster_id === null) return "#de2d26";
  if (node.cluster_id === 0) return "#de2d26"; // baseline cluster, no distinct pattern
  return CLUSTER_PALETTE[node.cluster_id % CLUSTER_PALETTE.length];
}

export default function NetworkGraph({ topN, maxIncidentsPerSuspect, district }) {
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const containerRef = useRef(null);
  const [dimensions, setDimensions] = useState({ width: 600, height: 500 });

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    params.set("top_n_suspects", topN);
    params.set("max_incidents_per_suspect", maxIncidentsPerSuspect);
    if (district) params.set("district", district);

    fetch(`http://localhost:8000/api/network?${params.toString()}`)
      .then((res) => {
        if (!res.ok) throw new Error(`API returned ${res.status}`);
        return res.json();
      })
      .then((data) => {
        // react-force-graph mutates node objects in place to add x/y/vx/vy — copy
        // to avoid accidentally sharing references if this effect re-runs.
        setGraphData({
          nodes: data.nodes.map((n) => ({ ...n })),
          links: data.links.map((l) => ({ ...l })),
        });
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [topN, maxIncidentsPerSuspect, district]);

  useEffect(() => {
    if (!containerRef.current) return undefined;
    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setDimensions({ width, height });
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  const clusterCounts = useMemo(() => {
    const counts = {};
    graphData.nodes.forEach((n) => {
      if (n.type === "suspect") {
        counts[n.cluster_id] = (counts[n.cluster_id] || 0) + 1;
      }
    });
    return counts;
  }, [graphData.nodes]);

  if (error) return <p style={{ color: "red", padding: 20 }}>Error: {error}</p>;

  return (
    <div style={{ display: "flex", height: "100%", width: "100%" }}>
      <div ref={containerRef} style={{ flex: 1, position: "relative" }}>
        {loading && <div className="loading-banner">Loading network...</div>}
        <ForceGraph2D
          graphData={graphData}
          width={dimensions.width}
          height={dimensions.height}
          nodeLabel={(n) => `${n.label} (${n.type})`}
          nodeColor={(n) => (n.type === "suspect" ? suspectColor(n) : NODE_COLORS[n.type])}
          nodeVal={(n) => (n.type === "suspect" ? 6 : n.type === "station" ? 5 : 2)}
          linkColor={() => "rgba(150,150,150,0.35)"}
          linkWidth={(l) => Math.min(3, 0.5 + l.weight * 0.3)}
          onNodeClick={(n) => setSelectedNode(n)}
          cooldownTicks={80}
        />
      </div>

      <div className="graph-sidebar">
        <h4>Legend</h4>
        <p className="muted">
          Suspects colored by MO-similarity cluster (cosine similarity on weapon,
          target, escape pattern, day/night — see backend/mo_clustering.py). Cluster
          0 is the baseline "no strong shared pattern" group; other colors indicate a
          suspect group whose MO signature is distinctly similar to each other.
        </p>
        <ul className="cluster-legend">
          {Object.entries(clusterCounts).map(([cid, count]) => (
            <li key={cid}>
              <span
                className="dot"
                style={{
                  background: cid === "0" ? "#de2d26" : CLUSTER_PALETTE[cid % CLUSTER_PALETTE.length],
                }}
              />
              Cluster {cid}: {count} suspect{count !== 1 ? "s" : ""}
              {cid !== "0" && count > 1 && <strong> — shared MO group</strong>}
            </li>
          ))}
        </ul>

        {selectedNode && (
          <div className="node-detail">
            <h4>{selectedNode.label}</h4>
            <p className="muted">Type: {selectedNode.type}</p>
            {selectedNode.type === "suspect" && (
              <>
                <p className="muted">Total incidents: {selectedNode.total_incident_count}</p>
                <p className="muted">Dominant weapon/method: {selectedNode.dominant_weapon}</p>
                <p className="muted">MO cluster: {selectedNode.cluster_id}</p>
              </>
            )}
          </div>
        )}

        <p className="muted graph-note">
          Showing top {topN} most active suspects, up to {maxIncidentsPerSuspect} sampled
          incidents each — this is a readability cap, not the full dataset. See README
          for why (150 suspects share ~21,700 incidents, so an absolute activity
          threshold doesn't scale — this uses relative top-N filtering instead).
        </p>
      </div>
    </div>
  );
}
