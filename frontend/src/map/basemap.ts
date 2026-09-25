import type { StyleSpecification } from "maplibre-gl";

/**
 * GTA-V-like basemap: flat dark desaturated green land, pale glowing water,
 * thin light roads, sparse spaced-out labels. Vector tiles: OpenFreeMap (OpenMapTiles schema).
 */
export const C = {
  land: "#17221c",
  landDeep: "#121b16",
  forest: "#1d2c23",
  park: "#1b2920",
  urban: "#1f2a24",
  building: "#26332c",
  water: "#9fb4ad",
  waterGlow: "#cfe3dc",
  road: "#7f938a",
  roadMajor: "#b3c4bc",
  rail: "#56675f",
  border: "#a9c9b8",
  label: "#c9d8d0",
  labelHalo: "#0e1612",
};

const FONT = ["Noto Sans Regular"];
const FONT_BOLD = ["Noto Sans Bold"];
const NAME = ["coalesce", ["get", "name:pl"], ["get", "name"]];

export function gtaStyle(): StyleSpecification {
  return {
    version: 8,
    glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
    sources: {
      omt: {
        type: "vector",
        url: "https://tiles.openfreemap.org/planet",
        attribution: '<a href="https://openfreemap.org">OpenFreeMap</a> © <a href="https://www.openmaptiles.org/">OpenMapTiles</a> © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      },
    },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": C.land } },
      {
        id: "landcover-wood", type: "fill", source: "omt", "source-layer": "landcover",
        filter: ["==", ["get", "class"], "wood"],
        paint: { "fill-color": C.forest, "fill-antialias": false },
      },
      {
        id: "landcover-wet", type: "fill", source: "omt", "source-layer": "landcover",
        filter: ["==", ["get", "class"], "wetland"],
        paint: { "fill-color": "#1a2a26", "fill-antialias": false },
      },
      {
        id: "park", type: "fill", source: "omt", "source-layer": "park",
        paint: { "fill-color": C.park, "fill-opacity": 0.6 },
      },
      {
        id: "landuse-urban", type: "fill", source: "omt", "source-layer": "landuse",
        filter: ["in", ["get", "class"], ["literal", ["residential", "industrial", "commercial", "retail"]]],
        paint: { "fill-color": C.urban, "fill-opacity": ["interpolate", ["linear"], ["zoom"], 8, 0.4, 13, 0.9] },
      },
      // soft glow around water (GTA coastline look)
      {
        id: "water-glow", type: "line", source: "omt", "source-layer": "water",
        paint: {
          "line-color": C.waterGlow,
          "line-blur": ["interpolate", ["linear"], ["zoom"], 5, 3, 12, 10],
          "line-width": ["interpolate", ["linear"], ["zoom"], 5, 3, 12, 12],
          "line-opacity": 0.35,
        },
      },
      {
        id: "water", type: "fill", source: "omt", "source-layer": "water",
        paint: { "fill-color": C.water },
      },
      {
        id: "waterway", type: "line", source: "omt", "source-layer": "waterway",
        filter: ["in", ["get", "class"], ["literal", ["river", "canal"]]],
        paint: {
          "line-color": C.water,
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 0.6, 14, 3],
        },
      },
      {
        id: "building", type: "fill", source: "omt", "source-layer": "building", minzoom: 13,
        paint: { "fill-color": C.building, "fill-opacity": 0.8 },
      },
      {
        id: "rail", type: "line", source: "omt", "source-layer": "transportation", minzoom: 9,
        filter: ["==", ["get", "class"], "rail"],
        paint: { "line-color": C.rail, "line-width": 0.8, "line-dasharray": [3, 2] },
      },
      {
        id: "roads-minor", type: "line", source: "omt", "source-layer": "transportation", minzoom: 11,
        filter: ["in", ["get", "class"], ["literal", ["minor", "service", "track"]]],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": C.road,
          "line-opacity": 0.55,
          "line-width": ["interpolate", ["linear"], ["zoom"], 11, 0.3, 16, 2],
        },
      },
      {
        id: "roads-mid", type: "line", source: "omt", "source-layer": "transportation", minzoom: 8,
        filter: ["in", ["get", "class"], ["literal", ["secondary", "tertiary"]]],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": C.road,
          "line-opacity": 0.8,
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 0.4, 16, 3],
        },
      },
      {
        id: "roads-major", type: "line", source: "omt", "source-layer": "transportation", minzoom: 5,
        filter: ["in", ["get", "class"], ["literal", ["motorway", "trunk", "primary"]]],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": C.roadMajor,
          "line-opacity": 0.85,
          "line-width": ["interpolate", ["linear"], ["zoom"], 5, 0.5, 10, 1.4, 16, 5],
        },
      },
      {
        id: "border-country", type: "line", source: "omt", "source-layer": "boundary",
        filter: ["all", ["==", ["get", "admin_level"], 2], ["!=", ["get", "maritime"], 1]],
        paint: { "line-color": C.border, "line-width": 1.2, "line-opacity": 0.55, "line-dasharray": [4, 2] },
      },
      {
        id: "border-region", type: "line", source: "omt", "source-layer": "boundary", minzoom: 6,
        filter: ["==", ["get", "admin_level"], 4],
        paint: { "line-color": C.border, "line-width": 0.6, "line-opacity": 0.25 },
      },
      {
        id: "label-road", type: "symbol", source: "omt", "source-layer": "transportation_name", minzoom: 13,
        layout: {
          "symbol-placement": "line", "text-field": NAME as never, "text-font": FONT,
          "text-size": 10, "text-letter-spacing": 0.08,
        },
        paint: { "text-color": C.label, "text-halo-color": C.labelHalo, "text-halo-width": 1.2, "text-opacity": 0.7 },
      },
      {
        id: "label-water", type: "symbol", source: "omt", "source-layer": "water_name", minzoom: 9,
        layout: { "text-field": NAME as never, "text-font": FONT, "text-size": 11, "text-letter-spacing": 0.15 },
        paint: { "text-color": "#e2efe9", "text-halo-color": "#5d7169", "text-halo-width": 1 },
      },
      {
        id: "label-village", type: "symbol", source: "omt", "source-layer": "place", minzoom: 10,
        filter: ["in", ["get", "class"], ["literal", ["village", "hamlet", "suburb"]]],
        layout: {
          "text-field": NAME as never, "text-font": FONT, "text-size": 11,
          "text-letter-spacing": 0.06,
        },
        paint: { "text-color": C.label, "text-halo-color": C.labelHalo, "text-halo-width": 1.4, "text-opacity": 0.8 },
      },
      {
        id: "label-town", type: "symbol", source: "omt", "source-layer": "place", minzoom: 7,
        filter: ["==", ["get", "class"], "town"],
        layout: {
          "text-field": NAME as never, "text-font": FONT, "text-size": 12,
          "text-transform": "uppercase", "text-letter-spacing": 0.12,
        },
        paint: { "text-color": C.label, "text-halo-color": C.labelHalo, "text-halo-width": 1.5 },
      },
      {
        id: "label-city", type: "symbol", source: "omt", "source-layer": "place", minzoom: 4,
        filter: ["==", ["get", "class"], "city"],
        layout: {
          "text-field": NAME as never, "text-font": FONT_BOLD,
          "text-size": ["interpolate", ["linear"], ["zoom"], 5, 11, 10, 16],
          "text-transform": "uppercase", "text-letter-spacing": 0.2,
        },
        paint: { "text-color": "#e6f0ea", "text-halo-color": C.labelHalo, "text-halo-width": 1.8 },
      },
    ],
  };
}

/** Fallback if vector tiles fail: OSM raster, desaturated and darkened over the green land colour. */
export function rasterFallbackStyle(): StyleSpecification {
  return {
    version: 8,
    sources: {
      osm: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        attribution: "© OpenStreetMap contributors",
      },
    },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": C.land } },
      {
        id: "osm", type: "raster", source: "osm",
        paint: {
          "raster-saturation": -1,
          "raster-contrast": 0.1,
          "raster-brightness-max": 0.55,
          "raster-opacity": 0.45,
        },
      },
    ],
  };
}
