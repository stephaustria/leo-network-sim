import { fmtTime, num, pct } from "../utils";

export default function MetricsPanel({ frame }) {
  const m = frame?.metrics;
  const cards = [
    ["Sim time", frame ? fmtTime(frame.t) : "–"],
    ["Flows reachable", m ? `${m.flows_reachable}/${m.flows_total}` : "–"],
    ["Delivery", pct(m?.delivery_ratio)],
    ["Mean latency", m?.mean_latency_ms != null ? `${num(m.mean_latency_ms)} ms` : "–"],
    ["Max link util", pct(m?.max_link_util, 0)],
    ["Congested / overloaded", m ? `${m.congested_links} / ${m.overloaded_links}` : "–"],
    ["Handoffs (tick)", m ? m.handoffs : "–"],
    ["Links added / removed", m ? `${m.links_added} / ${m.links_removed}` : "–"],
  ];
  return (
    <div className="panel">
      <h3>Metrics</h3>
      <div className="cards">
        {cards.map(([label, value]) => (
          <div className="card" key={label}>
            <div className="card-label">{label}</div>
            <div className="card-value">{value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}