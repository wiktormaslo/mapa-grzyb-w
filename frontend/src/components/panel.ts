import type { PointPrediction, PointResponse } from "../types";
import { classFor } from "../map/scale";
import { MISSING, NEGATIVE, POSITIVE, text } from "./messages";

const panel = () => document.getElementById("panel") as HTMLElement;

const esc = (s: unknown) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

const fmt = (v: unknown, unit = "", digits = 0) =>
  v === null || v === undefined || v === "" ? "brak danych" : `${Number(v).toFixed(digits)}${unit}`;

function list(title: string, codes: string[], dict: Record<string, string>, cls: string) {
  if (!codes.length) return "";
  return `<h4>${title}</h4><ul class="${cls}">${codes.map((c) => `<li>${esc(text(dict, c))}</li>`).join("")}</ul>`;
}

function speciesBlock(p: PointPrediction, open: boolean) {
  const f = p.features;
  const cls = classFor(p.score);
  return `
  <details class="sp" ${open ? "open" : ""}>
    <summary>
      <span class="sp-name">${esc(p.name_pl.toUpperCase())}</span>
      <span class="badge" style="background:${cls.color};color:${p.score >= 60 ? "#fff" : "#222"}">${p.score}/100</span>
    </summary>
    <div class="kv"><span>Indeks sprzyjających warunków</span><b>${p.score}/100 (${cls.label})</b></div>
    <div class="kv"><span>Pewność</span><b>${p.confidence}/100</b></div>
    ${list("Dlaczego wysoko", p.positive_factors, POSITIVE, "pos")}
    ${list("Co obniża wynik", p.negative_factors, NEGATIVE, "neg")}
    <h4>Pogoda i gleba</h4>
    <div class="kv"><span>Opad 7 / 14 / 30 dni</span><b>${fmt(f.rain_7d)} / ${fmt(f.rain_14d)} / ${fmt(f.rain_30d, " mm")}</b></div>
    <div class="kv"><span>Dni od opadu ≥10 mm</span><b>${fmt(f.days_since_rain_10mm)}</b></div>
    <div class="kv"><span>Temperatura śr. 7 / 14 dni</span><b>${fmt(f.temperature_mean_7d, "", 1)} / ${fmt(f.temperature_mean_14d, " °C", 1)}</b></div>
    <div class="kv"><span>Wilgotność gleby (7 dni)</span><b>${fmt(f.soil_moisture_mean_7d, " m³/m³", 2)}</b></div>
    <div class="kv"><span>Temperatura gleby</span><b>${fmt(f.soil_temperature, " °C", 1)}</b></div>
    <div class="kv"><span>Wilgotność powietrza / VPD</span><b>${fmt(f.humidity, " %")} / ${fmt(f.vpd, " kPa", 2)}</b></div>
    <div class="kv"><span>Bilans wodny 14 dni</span><b>${fmt(f.water_balance_14d, " mm")}</b></div>
    ${list("Brakujące dane (obniżają pewność)", p.missing_data, MISSING, "miss")}
  </details>`;
}

export function showLoading(lat: number, lon: number) {
  const el = panel();
  el.hidden = false;
  el.innerHTML = `<button class="close" aria-label="Zamknij">×</button>
    <p class="muted">Analiza punktu ${lat.toFixed(4)}, ${lon.toFixed(4)}…</p>`;
  bindClose();
}

export function showError(msg: string) {
  const el = panel();
  el.hidden = false;
  el.innerHTML = `<button class="close" aria-label="Zamknij">×</button><p class="err">${esc(msg)}</p>`;
  bindClose();
}

export function showPoint(r: PointResponse) {
  const el = panel();
  el.hidden = false;
  let html = `<button class="close" aria-label="Zamknij">×</button>`;
  html += `<p class="muted">${r.lat.toFixed(4)}, ${r.lon.toFixed(4)} · ${esc(r.date)}</p>`;
  if (r.errors.length) html += `<p class="err">Problemy ze źródłami: ${r.errors.map(esc).join("; ")}</p>`;
  if (!r.in_forest) {
    html += r.errors.some((e) => e.startsWith("bdl"))
      ? `<p>Nie udało się pobrać danych leśnych (BDL) – brak wyniku.</p>`
      : `<p>W tym punkcie nie ma wydzielenia leśnego Lasów Państwowych w BDL. Indeks liczony jest tylko dla lasów z danymi o drzewostanie.</p>`;
    el.innerHTML = html;
    bindClose();
    return;
  }
  const fo = r.forest!;
  const trees = fo.trees.length
    ? fo.trees.map((t) => `${esc(t.name_pl)}${t.share !== null ? ` ${Math.round(t.share * 100)}%` : ""}`).join(", ")
    : "brak danych";
  html += `<h3>Drzewostan</h3>
    <div class="kv"><span>Dominujące drzewa</span><b>${trees}</b></div>
    <div class="kv"><span>Siedlisko</span><b>${esc(fo.site_type_label ?? fo.site_type ?? "brak danych")}</b></div>
    <div class="kv"><span>Wiek drzewostanu</span><b>${fmt(fo.stand_age, " lat")}</b></div>
    ${fo.address ? `<div class="kv"><span>Adres leśny</span><b>${esc(fo.address)}</b></div>` : ""}`;
  html += r.results.map((p, i) => speciesBlock(p, i === 0)).join("");
  html += `<p class="muted small">Źródła: ${r.sources.map(esc).join(", ") || "—"}.<br>
    Indeks to heurystyczna ocena warunków (0–100), nie prawdopodobieństwo znalezienia grzybów.</p>`;
  el.innerHTML = html;
  bindClose();
}

function bindClose() {
  panel().querySelector(".close")?.addEventListener("click", () => (panel().hidden = true));
}
