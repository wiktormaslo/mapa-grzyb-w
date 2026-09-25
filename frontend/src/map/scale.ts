/**
 * One colour ramp for the whole app: heat "liquid" on the map, legend, score badges.
 * Low values are cool and nearly transparent, high values hot and bright, so good places
 * pop out of the dark green basemap.
 */
export const RAMP: [number, string][] = [
  [0, "rgba(96, 86, 255, 0)"],
  [15, "rgba(106, 94, 255, 0.2)"],
  [30, "rgba(92, 132, 255, 0.36)"],
  [45, "rgba(52, 222, 255, 0.48)"],
  [60, "rgba(176, 255, 64, 0.58)"],
  [75, "rgba(255, 226, 58, 0.66)"],
  [90, "rgba(255, 128, 44, 0.72)"],
  [100, "rgba(255, 70, 70, 0.78)"],
];

export const CLASSES = [
  { min: 0, max: 20, label: "bardzo słabe" },
  { min: 20, max: 40, label: "słabe" },
  { min: 40, max: 60, label: "umiarkowane" },
  { min: 60, max: 80, label: "dobre" },
  { min: 80, max: 101, label: "bardzo dobre" },
];

export function classFor(score: number) {
  return CLASSES.find((c) => score >= c.min && score < c.max) ?? CLASSES[0];
}

function parse(c: string): number[] {
  return c.match(/[\d.]+/g)!.map(Number);
}

/** Solid (opaque) colour for a score - for UI badges, rings, bars. */
export function colorFor(score: number): string {
  const s = Math.max(0, Math.min(100, score));
  for (let i = 1; i < RAMP.length; i++) {
    const [x1, c1] = RAMP[i];
    const [x0, c0] = RAMP[i - 1];
    if (s <= x1) {
      const t = (s - x0) / (x1 - x0);
      const a = parse(c0), b = parse(c1);
      const mix = (k: number) => Math.round(a[k] + (b[k] - a[k]) * t);
      return `rgb(${mix(0)}, ${mix(1)}, ${mix(2)})`;
    }
  }
  return "rgb(255, 70, 70)";
}

export function cssGradient(): string {
  const stops = RAMP.slice(1).map(([x, c]) => {
    const [r, g, b] = parse(c);
    return `rgb(${r},${g},${b}) ${x}%`;
  });
  return `linear-gradient(90deg, ${stops.join(", ")})`;
}
