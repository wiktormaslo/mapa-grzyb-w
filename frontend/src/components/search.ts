/**
 * Place search. Photon (komoot, OSM data) supports search-as-you-type and CORS;
 * results are limited to Poland. "52.1, 21.3" style coordinates work too.
 * If Photon fails, Nominatim is used - only on Enter, as its policy forbids autocomplete.
 */
export interface Place {
  name: string;
  detail: string;
  lat: number;
  lon: number;
  bbox?: [number, number, number, number]; // w, s, e, n
}

const PHOTON = "https://photon.komoot.io/api/";
const NOMINATIM = "https://nominatim.openstreetmap.org/search";
const PL_BBOX = "14.0,49.0,24.2,54.9";
const COORDS = /^\s*(-?\d{1,2}(?:[.,]\d+)?)\s*[,;\s]\s*(-?\d{1,3}(?:[.,]\d+)?)\s*$/;

const TYPE_PL: Record<string, string> = {
  city: "miasto", town: "miasto", village: "wieś", hamlet: "osada", suburb: "dzielnica",
  forest: "las", wood: "las", peak: "szczyt", lake: "jezioro", water: "woda",
  nature_reserve: "rezerwat", national_park: "park narodowy", protected_area: "obszar chroniony",
  county: "powiat", state: "województwo", locality: "miejscowość", street: "ulica",
};

async function query(q: string, signal: AbortSignal, explicit = false): Promise<Place[]> {
  const m = q.match(COORDS);
  if (m) {
    const lat = parseFloat(m[1].replace(",", ".")), lon = parseFloat(m[2].replace(",", "."));
    if (Math.abs(lat) <= 90 && Math.abs(lon) <= 180) {
      return [{ name: `${lat.toFixed(5)}, ${lon.toFixed(5)}`, detail: "współrzędne", lat, lon }];
    }
  }
  try {
    return await photon(q, signal);
  } catch (e) {
    if ((e as Error).name === "AbortError" || !explicit) throw e;
    return nominatim(q, signal); // fallback when Photon is down (explicit search only)
  }
}

async function nominatim(q: string, signal: AbortSignal): Promise<Place[]> {
  const url = `${NOMINATIM}?${new URLSearchParams({
    q, format: "jsonv2", countrycodes: "pl", limit: "7", "accept-language": "pl",
  })}`;
  const r = await fetch(url, { signal });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const rows = await r.json();
  return rows.map((x: any) => {
    const bb = (x.boundingbox ?? []).map(Number); // [s, n, w, e]
    const parts = String(x.display_name ?? "").split(", ");
    return {
      name: x.name || parts[0],
      detail: [TYPE_PL[x.type] ?? "", parts.slice(1, 4).join(", ")].filter(Boolean).join(" · "),
      lat: Number(x.lat), lon: Number(x.lon),
      bbox: bb.length === 4 ? [bb[2], bb[0], bb[3], bb[1]] : undefined,
    } as Place;
  });
}

async function photon(q: string, signal: AbortSignal): Promise<Place[]> {
  const url = `${PHOTON}?${new URLSearchParams({ q, limit: "7", bbox: PL_BBOX })}`;
  const r = await fetch(url, { signal });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const body = await r.json();
  return (body.features ?? []).map((f: any) => {
    const p = f.properties ?? {};
    const [lon, lat] = f.geometry.coordinates;
    const kind = TYPE_PL[p.osm_value] ?? TYPE_PL[p.type] ?? "";
    const where = [p.city !== p.name ? p.city : null, p.county, p.state].filter(Boolean).join(", ");
    const ext = p.extent as number[] | undefined; // [minLon, maxLat, maxLon, minLat]
    return {
      name: p.name ?? p.street ?? "?",
      detail: [kind, where].filter(Boolean).join(" · "),
      lat, lon,
      bbox: ext ? [ext[0], ext[3], ext[2], ext[1]] : undefined,
    } as Place;
  });
}

export function initSearch(root: HTMLElement, onPick: (p: Place) => void) {
  root.innerHTML = `
    <div class="search-box">
      <svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/></svg>
      <input type="search" placeholder="Szukaj miejsca, lasu, współrzędnych…" autocomplete="off"
        aria-label="Szukaj lokalizacji" />
      <kbd>/</kbd>
    </div>
    <ul class="search-results" role="listbox" hidden></ul>`;
  const input = root.querySelector("input")!;
  const list = root.querySelector(".search-results") as HTMLUListElement;
  let items: Place[] = [];
  let active = -1;
  let timer: number | undefined;
  let ctrl: AbortController | null = null;

  const close = () => { list.hidden = true; active = -1; };
  const pick = (p: Place) => {
    input.value = p.name;
    close();
    input.blur();
    onPick(p);
  };
  const render = () => {
    list.innerHTML = items.length
      ? items.map((p, i) => `<li role="option" data-i="${i}" class="${i === active ? "on" : ""}">
          <b>${esc(p.name)}</b><span>${esc(p.detail)}</span></li>`).join("")
      : `<li class="empty">Brak wyników</li>`;
    list.hidden = false;
  };

  input.addEventListener("input", () => {
    window.clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 3) { close(); return; }
    timer = window.setTimeout(async () => {
      ctrl?.abort();
      ctrl = new AbortController();
      try {
        items = await query(q, ctrl.signal);
        active = items.length ? 0 : -1;
        render();
      } catch (e) {
        if ((e as Error).name !== "AbortError") {
          items = [];
          list.innerHTML = `<li class="empty">Podpowiedzi niedostępne – naciśnij Enter, aby wyszukać</li>`;
          list.hidden = false;
        }
      }
    }, 350);
  });
  input.addEventListener("keydown", async (e) => {
    if (list.hidden || !items.length) {
      if (e.key === "Escape") input.blur();
      if (e.key === "Enter" && input.value.trim().length >= 2) {
        // explicit search (also the Nominatim fallback path)
        e.preventDefault();
        window.clearTimeout(timer);
        ctrl?.abort();
        ctrl = new AbortController();
        try {
          items = await query(input.value.trim(), ctrl.signal, true);
          if (items.length === 1) pick(items[0]);
          else { active = items.length ? 0 : -1; render(); }
        } catch (err) {
          if ((err as Error).name !== "AbortError") {
            list.innerHTML = `<li class="empty">Wyszukiwarka niedostępna</li>`;
            list.hidden = false;
          }
        }
      }
      return;
    }
    if (e.key === "ArrowDown") { active = (active + 1) % items.length; render(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { active = (active - 1 + items.length) % items.length; render(); e.preventDefault(); }
    else if (e.key === "Enter" && active >= 0) { pick(items[active]); e.preventDefault(); }
    else if (e.key === "Escape") close();
  });
  list.addEventListener("mousedown", (e) => {
    const li = (e.target as HTMLElement).closest("li[data-i]") as HTMLElement | null;
    if (li) pick(items[Number(li.dataset.i)]);
  });
  input.addEventListener("blur", () => setTimeout(close, 150));
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement !== input) {
      e.preventDefault();
      input.focus();
    }
  });
}

function esc(s: unknown) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}
