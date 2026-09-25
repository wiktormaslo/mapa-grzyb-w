import type { BboxResponse, PointResponse, SpeciesResponse } from "../types";

const BASE = "/api/v1";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(url, { signal });
  if (!r.ok) {
    let detail = `HTTP ${r.status}`;
    try {
      const body = await r.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }
  return (await r.json()) as T;
}

/**
 * Free Render instances sleep when idle; the first request can take ~30-60 s
 * or fail with 502/503 while the server boots. Retry calmly a few times.
 */
export async function waitForServer(onSlow: () => void): Promise<SpeciesResponse> {
  const slowTimer = setTimeout(onSlow, 1500);
  const delays = [3000, 5000, 8000, 10000, 15000, 20000];
  try {
    for (let attempt = 0; ; attempt++) {
      try {
        return await getJson<SpeciesResponse>(`${BASE}/species`);
      } catch (e) {
        onSlow();
        if (attempt >= delays.length) throw e;
        await sleep(delays[attempt]);
      }
    }
  } finally {
    clearTimeout(slowTimer);
  }
}

export function fetchBbox(
  p: { west: number; south: number; east: number; north: number; zoom: number; species: string; date: string },
  signal: AbortSignal,
): Promise<BboxResponse> {
  const q = new URLSearchParams({
    west: p.west.toFixed(5),
    south: p.south.toFixed(5),
    east: p.east.toFixed(5),
    north: p.north.toFixed(5),
    zoom: p.zoom.toFixed(2),
    species: p.species,
    date: p.date,
  });
  return getJson<BboxResponse>(`${BASE}/predictions/bbox?${q}`, signal);
}

export function fetchPoint(
  p: { lat: number; lon: number; species: string; date: string },
  signal: AbortSignal,
): Promise<PointResponse> {
  const q = new URLSearchParams({
    lat: p.lat.toFixed(6),
    lon: p.lon.toFixed(6),
    species: p.species,
    date: p.date,
  });
  return getJson<PointResponse>(`${BASE}/prediction?${q}`, signal);
}
