import { useEffect } from "react";
import { useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet.heat";

/**
 * Renders a leaflet.heat heatmap layer from an array of {lat, long} points.
 * leaflet.heat isn't an ESM-friendly React component itself, so we wrap it
 * imperatively using react-leaflet's useMap hook and clean up on unmount/update.
 */
export default function HeatmapLayer({ points }) {
  const map = useMap();

  useEffect(() => {
    if (!points || points.length === 0) return undefined;
    const heatPoints = points.map((p) => [p.lat, p.long, 0.5]);
    const heatLayer = L.heatLayer(heatPoints, { radius: 20, blur: 25, maxZoom: 12 });
    heatLayer.addTo(map);
    return () => {
      map.removeLayer(heatLayer);
    };
  }, [map, points]);

  return null;
}
