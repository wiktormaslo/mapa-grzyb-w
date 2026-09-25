export const CLASSES = [
  { min: 0, max: 20, label: "bardzo słabe", color: "#f2efe4" },
  { min: 20, max: 40, label: "słabe", color: "#d9ef8b" },
  { min: 40, max: 60, label: "umiarkowane", color: "#a6d96a" },
  { min: 60, max: 80, label: "dobre", color: "#1a9850" },
  { min: 80, max: 101, label: "bardzo dobre", color: "#00441b" },
];

export function classFor(score: number) {
  return CLASSES.find((c) => score >= c.min && score < c.max) ?? CLASSES[0];
}
