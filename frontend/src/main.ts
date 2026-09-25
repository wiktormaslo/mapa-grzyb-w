import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import "./style.css";
import { fetchBbox, fetchPoint, fillWeatherGap, waitForServer } from "./api/client";
import { C as BASE, gtaStyle, rasterFallbackStyle } from "./map/basemap";
import { addPredictionLayers, setMode, setPredictions, type ViewMode } from "./map/layer";
import { CLASSES, cssGradient } from "./map/scale";
import { closePanel, onPanelClose, showError, showLoading, showPoint } from "./components/panel";
import { initSearch } from "./components/search";
import type { BboxResponse, SpeciesInfo } from "./types";

const state = {
  species: "all",
  date: "",
  mode: (localStorageGet("mode") as ViewMode) || "heat",
  speciesList: [] as SpeciesInfo[],
  ready: false,
  last: null as BboxResponse | null,
};

function localStorageGet(k: string) {
  try { return localStorage.getItem(k); } catch { return null; }
}
function localStorageSet(k: string, v: string) {
  try { localStorage.setItem(k, v); } catch { /* private mode */ }
}

// ------------------------------------------------------------------ status pill
const statusEl = document.getElementById("status")!;
function setStatus(msg: string, kind: "" | "err" | "busy" = "") {
  statusEl.textContent = msg;
  statusEl.className = kind;
  statusEl.hidden = !msg;
}

// ------------------------------------------------------------------ map
const map = new maplibregl.Map({
  container: "map",
  style: gtaStyle(),
  center: [21.35, 52.05],
  zoom: 10.5,
  minZoom: 5,
  maxZoom: 16,
  maxBounds: [[10, 46.5], [28.5, 57]],
  attributionControl: { compact: true },
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
map.addControl(new maplibregl.GeolocateControl({}), "bottom-right");

let usedFallback = false;
map.on("error", (e) => {
  const msg = String((e as { error?: Error }).error?.message ?? "");
  // vector basemap unavailable -> darkened OSM raster
  if (!usedFallback && /openfreemap|Failed to fetch|NetworkError|AJAXError/i.test(msg) && !map.isStyleLoaded()) {
    usedFallback = true;
    map.setStyle(rasterFallbackStyle());
  }
});
map.on("style.load", () => {
  addPredictionLayers(map, state.mode, usedFallback ? BASE.land : BASE.forest);
  if (state.last) setPredictions(map, state.last);
  if (state.ready) scheduleLoad(0);
});

// ------------------------------------------------------------------ pin
const pinEl = document.createElement("div");
pinEl.className = "pin";
pinEl.innerHTML = "<span></span>";
const pin = new maplibregl.Marker({ element: pinEl, anchor: "center" });
onPanelClose(() => pin.remove());

// ------------------------------------------------------------------ controls
function renderLegend() {
  document.getElementById("legend")!.innerHTML = `
    <div class="legend-bar" style="background:${cssGradient()}"></div>
    <div class="legend-ticks">${[0, 20, 40, 60, 80, 100].map((t) => `<span>${t}</span>`).join("")}</div>
    <div class="legend-labels">${CLASSES.map((c) => `<span>${c.label}</span>`).join("")}</div>
    <div class="legend-nodata"><i></i>las bez danych o drzewostanie (np. prywatny)</div>`;
}

function renderSpecies() {
  const box = document.getElementById("species")!;
  const opts = [{ id: "all", label: "Wszystkie", title: "Najwyższy wynik spośród 10 gatunków" }].concat(
    state.speciesList.map((s) => ({ id: s.id, label: s.name_short, title: `${s.name_pl} · ${s.latin}` })),
  );
  box.innerHTML = opts.map((o) =>
    `<button data-id="${o.id}" title="${o.title}" class="${state.species === o.id ? "on" : ""}">${o.label}</button>`).join("");
  box.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    state.species = (b as HTMLElement).dataset.id!;
    renderSpecies();
    scheduleLoad(0);
  }));
}

function renderDays(today: string, n: number) {
  const box = document.getElementById("days")!;
  const base = new Date(today + "T12:00:00");
  const days = Array.from({ length: n }, (_, i) => new Date(base.getTime() + i * 86400000));
  box.innerHTML = days.map((d, i) => {
    const iso = d.toISOString().slice(0, 10);
    const wd = i === 0 ? "dziś" : d.toLocaleDateString("pl-PL", { weekday: "short" }).replace(".", "");
    return `<button data-d="${iso}" class="${state.date === iso ? "on" : ""}"
      title="${d.toLocaleDateString("pl-PL", { weekday: "long", day: "numeric", month: "long" })}">
      <span>${wd}</span><b>${d.getDate()}</b></button>`;
  }).join("");
  box.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    state.date = (b as HTMLElement).dataset.d!;
    renderDays(today, n);
    scheduleLoad(0);
  }));
}

document.querySelectorAll<HTMLButtonElement>("#view button").forEach((b) => {
  b.classList.toggle("on", b.dataset.mode === state.mode);
  b.addEventListener("click", () => {
    state.mode = b.dataset.mode as ViewMode;
    localStorageSet("mode", state.mode);
    document.querySelectorAll("#view button").forEach((x) => x.classList.toggle("on", x === b));
    setMode(map, state.mode);
  });
});

const dock = document.getElementById("dock")!;
document.getElementById("dock-toggle")!.addEventListener("click", (e) => {
  const open = dock.classList.toggle("collapsed") === false;
  (e.currentTarget as HTMLElement).setAttribute("aria-expanded", String(open));
});
if (window.matchMedia("(max-width: 720px)").matches) dock.classList.add("collapsed");

initSearch(document.getElementById("search")!, (p) => {
  if (p.bbox && p.bbox[2] - p.bbox[0] > 0.01) {
    map.fitBounds([[p.bbox[0], p.bbox[1]], [p.bbox[2], p.bbox[3]]], { padding: 60, maxZoom: 13, duration: 1200 });
  } else {
    map.flyTo({ center: [p.lon, p.lat], zoom: 13, duration: 1200 });
  }
});

// ------------------------------------------------------------------ loading
let timer: number | undefined;
let controller: AbortController | null = null;

function scheduleLoad(delay = 400) {
  window.clearTimeout(timer);
  timer = window.setTimeout(load, delay);
}

function describe(data: BboxResponse) {
  const m = data.meta;
  const parts: string[] = [];
  if (m.resolution_m) parts.push(`siatka ${m.resolution_m >= 1000 ? m.resolution_m / 1000 + " km" : m.resolution_m + " m"}`);
  parts.push(`${m.cells} komórek leśnych`);
  if (m.cells && m.weather_source) {
    parts.push(m.weather_source === "open-meteo" && !m.weather_missing?.length ? "pogoda dokładna" : "pogoda przybliżona ~30 km");
  }
  return parts.join(" · ");
}

async function load() {
  if (!state.ready || !map.getSource("predictions")) return;
  controller?.abort();
  controller = new AbortController();
  const b = map.getBounds();
  setStatus("Liczenie indeksu…", "busy");
  try {
    const params = {
      west: b.getWest(), south: b.getSouth(), east: b.getEast(), north: b.getNorth(),
      zoom: map.getZoom(), species: state.species, date: state.date,
    };
    let data = await fetchBbox(params, controller.signal);
    state.last = data;
    setPredictions(map, data);
    if (data.meta.weather_missing?.length) {
      // server has no (or only ~30 km) weather here: fetch precise weather from this browser, retry once
      setStatus(data.features.length ? `${describe(data)} · doprecyzowuję pogodę…` : "Pobieranie pogody…", "busy");
      try {
        if (await fillWeatherGap(data.meta, controller.signal)) {
          data = await fetchBbox(params, controller.signal);
          state.last = data;
          setPredictions(map, data);
        }
      } catch (e) {
        if ((e as Error).name === "AbortError") throw e;
      }
    }
    const m = data.meta;
    if (m.errors.length) setStatus(`${describe(data)} · problemy ze źródłami: ${m.errors.join("; ")}`, "err");
    else setStatus(m.cells ? describe(data) : "Brak lasów państwowych w tym widoku");
  } catch (e) {
    if ((e as Error).name === "AbortError") return;
    setStatus(`Błąd pobierania danych: ${(e as Error).message}`, "err");
  }
}

map.on("moveend", () => scheduleLoad());

// ------------------------------------------------------------------ click vs double-click
// A double-click zooms; only a single click (no second click within the delay) opens details.
const DBL_MS = 280;
let clickTimer: number | undefined;
let pointController: AbortController | null = null;

map.on("click", (e) => {
  if (clickTimer !== undefined) {
    window.clearTimeout(clickTimer);
    clickTimer = undefined;
    return; // second click of a double-click
  }
  const at = e.lngLat;
  clickTimer = window.setTimeout(() => {
    clickTimer = undefined;
    openPoint(at.lat, at.lng);
  }, DBL_MS);
});
map.on("dblclick", () => {
  window.clearTimeout(clickTimer);
  clickTimer = undefined;
});

async function openPoint(lat: number, lon: number) {
  if (!state.ready) return;
  pointController?.abort();
  pointController = new AbortController();
  pin.setLngLat([lon, lat]).addTo(map);
  showLoading(lat, lon);
  try {
    const p = { lat, lon, species: state.species, date: state.date };
    let r = await fetchPoint(p, pointController.signal);
    if (r.weather_missing?.length && (await fillWeatherGap(r, pointController.signal).catch(() => false))) {
      r = await fetchPoint(p, pointController.signal);
    }
    showPoint(r);
  } catch (err) {
    if ((err as Error).name !== "AbortError") showError(`Błąd: ${(err as Error).message}`);
  }
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !(document.getElementById("panel") as HTMLElement).hidden) closePanel();
});

// ------------------------------------------------------------------ start
async function start() {
  renderLegend();
  setStatus("Łączenie z serwerem…", "busy");
  try {
    const info = await waitForServer(() =>
      setStatus("Uruchamianie serwera danych… (darmowy serwer budzi się do minuty)", "busy"));
    state.speciesList = info.species;
    state.date = info.today;
    renderSpecies();
    renderDays(info.today, info.forecast_days);
    state.ready = true;
    scheduleLoad(0);
  } catch {
    setStatus("Serwer danych nie odpowiada. Odśwież stronę za chwilę.", "err");
  }
}

start();
