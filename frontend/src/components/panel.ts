import type { PointPrediction, PointResponse } from "../types";
import { classFor, colorFor } from "../map/scale";
import { MISSING, NEGATIVE, POSITIVE, text } from "./messages";

const panel = () => document.getElementById("panel") as HTMLElement;
let onCloseCb: (() => void) | null = null;

export function onPanelClose(cb: () => void) {
  onCloseCb = cb;
}

const esc = (s: unknown) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

const num = (v: unknown, digits = 0) =>
  v === null || v === undefined || v === "" ? "—" : Number(v).toFixed(digits);

function ring(score: number) {
  const r = 46, c = 2 * Math.PI * r, col = colorFor(score);
  return `<svg class="ring" viewBox="0 0 110 110" aria-hidden="true">
    <circle cx="55" cy="55" r="${r}" class="ring-bg"/>
    <circle cx="55" cy="55" r="${r}" class="ring-fg" style="stroke:${col};filter:drop-shadow(0 0 8px ${col})"
      stroke-dasharray="${(c * score) / 100} ${c}" transform="rotate(-90 55 55)"/>
  </svg>`;
}

function factors(title: string, codes: string[], dict: Record<string, string>, cls: string) {
  if (!codes.length) return "";
  return `<section class="factors ${cls}"><h4>${title}</h4><ul>${codes
    .map((c) => `<li>${esc(text(dict, c))}</li>`).join("")}</ul></section>`;
}

function tile(label: string, value: string, unit = "") {
  return `<div class="tile"><span>${label}</span><b>${value}<small>${unit}</small></b></div>`;
}

function hero(p: PointPrediction) {
  const f = p.features;
  const cls = classFor(p.score);
  return `
    <div class="hero">
      <div class="hero-ring">${ring(p.score)}<div class="hero-num"><b>${p.score}</b><span>/100</span></div></div>
      <div class="hero-txt">
        <div class="eyebrow">Indeks warunków · ${cls.label}</div>
        <h2>${esc(p.name_pl)}</h2>
        <i>${esc(p.latin)}</i>
        <div class="conf" title="Pewność zależy od kompletności danych">
          <span>Pewność</span><div class="bar"><i style="width:${p.confidence}%"></i></div><b>${p.confidence}</b>
        </div>
      </div>
    </div>
    ${factors("Co sprzyja", p.positive_factors, POSITIVE, "pos")}
    ${factors("Co obniża", p.negative_factors, NEGATIVE, "neg")}
    <section>
      <h4>Pogoda i gleba</h4>
      <div class="tiles">
        ${tile("Opad 7 dni", num(f.rain_7d), " mm")}
        ${tile("Opad 14 dni", num(f.rain_14d), " mm")}
        ${tile("Opad 30 dni", num(f.rain_30d), " mm")}
        ${tile("Temp. 7 dni", num(f.temperature_mean_7d, 1), " °C")}
        ${tile("Temp. 14 dni", num(f.temperature_mean_14d, 1), " °C")}
        ${tile("Wilgotność gleby", num(f.soil_moisture_mean_7d, 2), " m³/m³")}
        ${tile("Temp. gleby", num(f.soil_temperature, 1), " °C")}
        ${tile("Wilg. powietrza", num(f.humidity), " %")}
        ${tile("VPD", num(f.vpd, 2), " kPa")}
        ${tile("Od opadu ≥10 mm", num(f.days_since_rain_10mm), " dni")}
        ${tile("Bilans wodny 14 d", num(f.water_balance_14d), " mm")}
      </div>
    </section>
    ${p.missing_data.length ? `<p class="missing">Brakujące dane: ${p.missing_data.map((c) => esc(text(MISSING, c))).join(" · ")}</p>` : ""}`;
}

function ranking(results: PointPrediction[], selected: string) {
  if (results.length < 2) return "";
  return `<section class="rank"><h4>Wszystkie gatunki w tym miejscu</h4><ol>${results
    .map((p) => `<li data-sp="${esc(p.species)}" class="${p.species === selected ? "on" : ""}">
        <span>${esc(p.name_pl)}</span>
        <div class="rbar"><i style="width:${p.score}%;background:${colorFor(p.score)}"></i></div>
        <b>${p.score}</b></li>`).join("")}</ol></section>`;
}

function shell(inner: string) {
  const el = panel();
  el.hidden = false;
  el.innerHTML = `<button class="close" aria-label="Zamknij panel">✕</button>${inner}`;
  el.querySelector(".close")!.addEventListener("click", closePanel);
  el.scrollTop = 0;
}

export function closePanel() {
  panel().hidden = true;
  onCloseCb?.();
}

export function showLoading(lat: number, lon: number) {
  shell(`<div class="loading"><span class="pulse"></span>Analiza miejsca
    <code>${lat.toFixed(4)}, ${lon.toFixed(4)}</code></div>`);
}

export function showError(msg: string) {
  shell(`<p class="err">${esc(msg)}</p>`);
}

export function showPoint(r: PointResponse) {
  const head = `<div class="where"><code>${r.lat.toFixed(4)}, ${r.lon.toFixed(4)}</code><span>${esc(r.date)}</span></div>`;
  const errs = r.errors.length ? `<p class="err">Problemy ze źródłami: ${r.errors.map(esc).join("; ")}</p>` : "";
  if (!r.in_forest) {
    const msg = r.errors.some((e) => e.startsWith("bdl"))
      ? "Nie udało się pobrać danych leśnych (BDL) – brak wyniku."
      : "Tu nie ma drzewostanu Lasów Państwowych w Banku Danych o Lasach. Indeks liczymy tylko tam, gdzie znamy las.";
    shell(`${head}${errs}<div class="empty-state"><h2>Poza lasem</h2><p>${msg}</p></div>`);
    return;
  }
  const fo = r.forest!;
  const trees = fo.trees.length
    ? fo.trees.map((t) => `${esc(t.name_pl)}${t.share !== null ? ` <b>${Math.round(t.share * 100)}%</b>` : ""}`).join(", ")
    : "brak danych";
  const forest = `<section class="forest">
      <h4>Drzewostan</h4>
      <div class="kv"><span>Drzewa</span><em>${trees}</em></div>
      <div class="kv"><span>Siedlisko</span><em>${esc(fo.site_type_label ?? fo.site_type ?? "brak danych")}</em></div>
      <div class="kv"><span>Wiek</span><em>${fo.stand_age !== null ? `${fo.stand_age} lat` : "brak danych"}</em></div>
      ${fo.address ? `<div class="kv"><span>Adres leśny</span><em class="mono">${esc(fo.address.replace(/\s+/g, ""))}</em></div>` : ""}
    </section>`;
  const foot = `<p class="foot">Źródła: ${r.sources.map(esc).join(" · ") || "—"}<br>
    Indeks to heurystyczna ocena warunków 0–100, nie prawdopodobieństwo znalezienia grzybów.</p>`;

  const render = (sp: string) => {
    const sel = r.results.find((p) => p.species === sp) ?? r.results[0];
    shell(`${head}${errs}${hero(sel)}${forest}${ranking(r.results, sel.species)}${foot}`);
    panel().querySelectorAll(".rank li").forEach((li) =>
      li.addEventListener("click", () => render((li as HTMLElement).dataset.sp!)));
  };
  render(r.results[0].species);
}
