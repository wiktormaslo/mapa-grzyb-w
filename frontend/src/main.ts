import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import "./style.css";
import { fetchBbox, fetchPoint, waitForServer } from "./api/client";
import { addPredictionLayer, setPredictions } from "./map/layer";
import { CLASSES } from "./map/scale";
import { showError, showLoading, showPoint } from "./components/panel";
import type { SpeciesInfo } from "./types";

const OSM_RASTER: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

const state = {
  species: "all",
  date: "",
  speciesList: [] as SpeciesInfo[],
  ready: false,
};

const statusEl = document.getElementById("status")!;
const setStatus = (msg: string, kind: "" | "err" | "busy" = "") => {
  statusEl.textContent = msg;
  statusEl.className = kind;
};

const map = new maplibregl.Map({
  container: "map",
  style: "https://tiles.openfreemap.org/styles/positron",
  center: [21.35, 52.05], // start small: Mazowsze near Warsaw
  zoom: 11,
  minZoom: 5,
  maxZoom: 16,
  maxBounds: [[10, 46.5], [28.5, 57]],
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
map.addControl(new maplibregl.GeolocateControl({}), "bottom-right");

let styleFallbackDone = false;
map.on("error", (e) => {
  // basemap unavailable -> fall back to plain OSM raster tiles
  if (!styleFallbackDone && !map.isStyleLoaded() && String(e.error?.message ?? "").match(/style|fetch|Failed/i)) {
    styleFallbackDone = true;
    map.setStyle(OSM_RASTER);
  }
});
map.on("style.load", () => {
  addPredictionLayer(map);
  if (state.ready) scheduleLoad(0);
});

// ------------------------------------------------------------------ controls
function renderLegend() {
  document.getElementById("legend")!.innerHTML =
    `<b>Indeks warunków</b>` +
    CLASSES.map((c) => `<div><i style="background:${c.color}"></i>${c.min}–${Math.min(c.max, 100)} ${c.label}</div>`).join("") +
    `<div class="small muted">bledszy kolor = mniejsza pewność</div>`;
}

function button(label: string, active: boolean, onClick: () => void, title = "") {
  const b = document.createElement("button");
  b.textContent = label;
  b.title = title;
  if (active) b.classList.add("active");
  b.addEventListener("click", onClick);
  return b;
}

function renderSpecies() {
  const box = document.getElementById("species-buttons")!;
  box.innerHTML = "";
  const opts = [{ id: "all", label: "Wszystkie", title: "Najwyższy wynik spośród 4 gatunków" }].concat(
    state.speciesList.map((s) => ({ id: s.id, label: s.name_short, title: `${s.name_pl} (${s.latin})` })),
  );
  for (const o of opts) {
    box.appendChild(button(o.label, state.species === o.id, () => {
      state.species = o.id;
      renderSpecies();
      scheduleLoad(0);
    }, o.title));
  }
}

function renderDates(today: string, days: number) {
  const box = document.getElementById("date-buttons")!;
  box.innerHTML = "";
  const base = new Date(today + "T12:00:00");
  for (let i = 0; i < days; i++) {
    const d = new Date(base.getTime() + i * 86400000);
    const iso = d.toISOString().slice(0, 10);
    const label = i === 0 ? "Dzisiaj" : `+${i}`;
    box.appendChild(button(label, state.date === iso, () => {
      state.date = iso;
      renderDates(today, days);
      scheduleLoad(0);
    }, d.toLocaleDateString("pl-PL", { weekday: "long", day: "numeric", month: "long" })));
  }
}

// ------------------------------------------------------------------ loading
let timer: number | undefined;
let controller: AbortController | null = null;

function scheduleLoad(delay = 400) {
  window.clearTimeout(timer);
  timer = window.setTimeout(load, delay);
}

async function load() {
  if (!state.ready || !map.getSource("predictions")) return;
  controller?.abort();
  controller = new AbortController();
  const b = map.getBounds();
  setStatus("Liczenie indeksu dla widocznego obszaru…", "busy");
  try {
    const data = await fetchBbox({
      west: b.getWest(), south: b.getSouth(), east: b.getEast(), north: b.getNorth(),
      zoom: map.getZoom(), species: state.species, date: state.date,
    }, controller.signal);
    setPredictions(map, data);
    const m = data.meta;
    const parts = [];
    if (m.resolution_m) parts.push(`siatka ${m.resolution_m >= 1000 ? m.resolution_m / 1000 + " km" : m.resolution_m + " m"}`);
    parts.push(`${m.cells} komórek leśnych`);
    if (m.errors.length) {
      setStatus(`${parts.join(" · ")} · problemy ze źródłami: ${m.errors.join("; ")}`, "err");
    } else {
      setStatus(m.cells ? parts.join(" · ") : "Brak lasów Lasów Państwowych w tym widoku (lub poza Polską).");
    }
  } catch (e) {
    if ((e as Error).name === "AbortError") return;
    setStatus(`Błąd pobierania danych: ${(e as Error).message}`, "err");
  }
}

map.on("moveend", () => scheduleLoad());

let pointController: AbortController | null = null;
map.on("click", async (e) => {
  if (!state.ready) return;
  pointController?.abort();
  pointController = new AbortController();
  const { lat, lng } = e.lngLat;
  showLoading(lat, lng);
  try {
    const r = await fetchPoint({ lat, lon: lng, species: state.species, date: state.date }, pointController.signal);
    showPoint(r);
  } catch (err) {
    if ((err as Error).name !== "AbortError") showError(`Błąd: ${(err as Error).message}`);
  }
});

// ------------------------------------------------------------------ start
async function start() {
  renderLegend();
  setStatus("Łączenie z serwerem…", "busy");
  try {
    const info = await waitForServer(() =>
      setStatus("Uruchamianie serwera danych… (darmowy serwer budzi się do ~1 min)", "busy"));
    state.speciesList = info.species;
    state.date = info.today;
    renderSpecies();
    renderDates(info.today, info.forecast_days);
    state.ready = true;
    scheduleLoad(0);
  } catch {
    setStatus("Serwer danych nie odpowiada. Odśwież stronę za chwilę.", "err");
  }
}

start();
