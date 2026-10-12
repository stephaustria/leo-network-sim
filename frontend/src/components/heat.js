import { num, pct } from "../utils";

const STOPS = [
  [0.0, [68, 1, 84]],
  [0.25, [59, 82, 139]],
  [0.5, [33, 144, 141]],
  [0.75, [93, 200, 99]],
  [1.0, [253, 231, 37]],
];

export function rampColor(t, alpha = 0.78) {
  const x = Math.max(0, Math.min(1, t));
  for (let i = 1; i < STOPS.length; i++) {
    if (x <= STOPS[i][0]) {
      const [t0, c0] = STOPS[i - 1];
      const [t1, c1] = STOPS[i];
      const f = (x - t0) / (t1 - t0);
      const c = c0.map((v, k) => Math.round(v + (c1[k] - v) * f));
      return `rgba(${c[0]},${c[1]},${c[2]},${alpha})`;
    }
  }
  return `rgba(253,231,37,${alpha})`;
}

export const HEAT_METRICS = [
  { key: "availability", label: "Availability", fixed: [0, 1], fmt: (v) => pct(v, 0) },
  { key: "mean_visible", label: "Satellites in view", fmt: (v) => num(v, 1) },
  { key: "mean_latency_ms", label: "Access latency", fmt: (v) => `${num(v, 1)} ms` },
  { key: "longest_gap_min", label: "Longest outage", fmt: (v) => `${num(v, 0)} min` },
];

function extent(values) {
  let lo = Infinity;
  let hi = -Infinity;
  for (const v of values) {
    if (v == null) continue;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  return lo === Infinity ? [0, 1] : [lo, hi];
}

export function makeHeatmap(coverage, metricKey, alpha = 0.78) {
  if (!coverage) return null;
  const metric = HEAT_METRICS.find((m) => m.key === metricKey) ?? HEAT_METRICS[0];
  const values = coverage[metric.key];
  const [min, max] = extent(values);
  const lo = metric.fixed ? metric.fixed[0] : metric.key === "mean_latency_ms" ? min : 0;
  const hi = metric.fixed ? metric.fixed[1] : Math.max(max, lo + 1e-9);
  return { grid: coverage.grid, values, metric, lo, hi, alpha };
}