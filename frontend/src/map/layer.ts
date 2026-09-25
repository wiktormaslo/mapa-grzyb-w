import type { GeoJSONSource, Map as MlMap } from "maplibre-gl";
import type { BboxResponse } from "../types";
import { CLASSES } from "./scale";

const SRC = "predictions";

export function addPredictionLayer(map: MlMap) {
  map.addSource(SRC, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  const color: unknown[] = ["step", ["get", "score"], CLASSES[0].color];
  for (const c of CLASSES.slice(1)) color.push(c.min, c.color);
  map.addLayer({
    id: "pred-fill",
    type: "fill",
    source: SRC,
    paint: {
      "fill-color": color as never,
      // lower confidence -> more transparent
      "fill-opacity": ["interpolate", ["linear"], ["get", "confidence"], 0, 0.35, 100, 0.8],
    },
  });
  map.addLayer({
    id: "pred-outline",
    type: "line",
    source: SRC,
    minzoom: 11,
    paint: { "line-color": "#ffffff", "line-width": 0.3, "line-opacity": 0.5 },
  });
}

export function setPredictions(map: MlMap, data: BboxResponse | null) {
  const src = map.getSource(SRC) as GeoJSONSource | undefined;
  src?.setData(data ?? { type: "FeatureCollection", features: [] });
}
