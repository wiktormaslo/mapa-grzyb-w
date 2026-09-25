import type { GeoJSONSource, Map as MlMap } from "maplibre-gl";
import type { BboxResponse } from "../types";
import { RAMP } from "./scale";

const SRC = "predictions";
const K = 2.2; // kernel radius in cell widths (wide enough that the grid does not show through)
// MapLibre heatmap kernel is a Gaussian with sigma = radius / 3. For points on a regular grid with
// spacing s and radius K*s the summed density is weight * intensity * sqrt(2*pi) * K^2 / 9,
// so this intensity makes a continuous forest of score S render as density S/100 (legend-true).
const INTENSITY = 9 / (Math.sqrt(2 * Math.PI) * K * K);

export type ViewMode = "heat" | "grid";

export function addPredictionLayers(map: MlMap, mode: ViewMode) {
  // big buffer: heatmap kernels are wider than MapLibre's default tile buffer, which would clip
  // blobs with straight edges at internal tile boundaries
  map.addSource(SRC, { type: "geojson", data: { type: "FeatureCollection", features: [] }, buffer: 512 });


  // density 0 = no analysed cell nearby -> fully transparent; any analysed forest -> faint tint
  const heatColor: unknown[] = ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(0,0,0,0)", 0.03, RAMP[0][1]];
  for (const [x, c] of RAMP.slice(1)) heatColor.push(x / 100, c);
  map.addLayer({
    id: "pred-heat",
    type: "heatmap",
    source: SRC,
    filter: ["==", ["geometry-type"], "Point"],
    layout: { visibility: mode === "heat" ? "visible" : "none" },
    paint: {
      // small floor so that even a 0-score forest shows the "analysed" tint
      "heatmap-weight": ["max", 0.06, ["/", ["get", "score"], 100]],
      "heatmap-intensity": INTENSITY,
      // pixel radius = K * cell width in px; cell width at zoom z = r0 * 2^z
      "heatmap-radius": ["interpolate", ["exponential", 2], ["zoom"],
        0, ["get", "r0"], 24, ["*", ["get", "r0"], 16777216]] as never,
      "heatmap-color": heatColor as never,
      "heatmap-opacity": 0.92,
    },
  });

  const fillColor: unknown[] = ["interpolate", ["linear"], ["get", "score"]];
  for (const [x, c] of RAMP) fillColor.push(x, c);
  map.addLayer({
    id: "pred-grid",
    type: "fill",
    source: SRC,
    filter: ["==", ["geometry-type"], "Polygon"],
    layout: { visibility: mode === "grid" ? "visible" : "none" },
    paint: { "fill-color": fillColor as never, "fill-outline-color": "rgba(10,20,15,0.35)" },
  });
}

export function setMode(map: MlMap, mode: ViewMode) {
  if (!map.getLayer("pred-heat")) return;
  map.setLayoutProperty("pred-heat", "visibility", mode === "heat" ? "visible" : "none");
  map.setLayoutProperty("pred-grid", "visibility", mode === "grid" ? "visible" : "none");
}

/** Cell centres (heatmap) + cell squares (grid view) from the compact API response. */
export function setPredictions(map: MlMap, data: BboxResponse | null) {
  const src = map.getSource(SRC) as GeoJSONSource | undefined;
  if (!src) return;
  if (!data || !data.meta.cell_deg) {
    src.setData({ type: "FeatureCollection", features: [] });
    return;
  }
  const [dlon, dlat] = data.meta.cell_deg;
  const r0 = (K * dlon * 512) / 360; // px at zoom 0 (MapLibre world = 512 px at z0)
  const features: object[] = [];
  for (const f of data.features) {
    const [lon, lat] = f.geometry.coordinates;
    const props = { ...f.properties, r0 };
    features.push({ type: "Feature", properties: props, geometry: f.geometry });
    const w = lon - dlon / 2, e = lon + dlon / 2, s = lat - dlat / 2, n = lat + dlat / 2;
    features.push({
      type: "Feature",
      properties: props,
      geometry: { type: "Polygon", coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] },
    });
  }
  src.setData({ type: "FeatureCollection", features } as never);
}
