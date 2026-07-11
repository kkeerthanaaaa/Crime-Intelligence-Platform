import { useEffect } from "react";
import { useMap } from "react-leaflet";

/** Flies the map to the given bounds whenever they change (used for district drill-down). */
export default function FlyToBounds({ bounds }) {
  const map = useMap();
  useEffect(() => {
    if (bounds) {
      map.flyToBounds(bounds, { duration: 0.8 });
    }
  }, [map, bounds]);
  return null;
}
