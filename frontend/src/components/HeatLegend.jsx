import { rampColor } from "./heat";

export default function HeatLegend({ heatmap }) {
  if (!heatmap) return null;
  const { metric, lo, hi } = heatmap;
  const stops = [0, 0.25, 0.5, 0.75, 1].map((t) => rampColor(t, 1)).join(", ");
  return (
    <div className="heat-legend">
      <span>{metric.fmt(lo)}</span>
      <div className="heat-bar" style={{ background: `linear-gradient(90deg, ${stops})` }} />
      <span>{metric.fmt(hi)}</span>
      <span className="dim">{metric.label}</span>
    </div>
  );
}