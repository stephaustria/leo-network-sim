import { useState } from "react";
import {
  CartesianGrid, Legend, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { fmtTime, num, pct } from "../utils";

const COLORS = ["#7aa2f7", "#6ee7a8", "#ffb454", "#ff6b9d", "#b794f6", "#4dd4e6"];

const METRICS = [
  { key: "goodput", label: "Goodput", fmt: (v) => pct(v, 1), domain: [0, 1] },
  { key: "mean_latency_ms", label: "Mean latency", fmt: (v) => `${num(v, 0)} ms` },
  { key: "mean_hops", label: "Mean hops", fmt: (v) => num(v, 1) },
  { key: "route_changes", label: "Route changes", fmt: (v) => num(v, 0) },
  { key: "overloaded_links", label: "Overloaded links", fmt: (v) => num(v, 0) },
  { key: "max_link_util", label: "Max link util", fmt: (v) => pct(v, 0) },
];

const COLUMNS = [
  { key: "mean_goodput", label: "Goodput", better: "max", fmt: (v) => pct(v, 1) },
  { key: "traffic_lost_gbit", label: "Lost Gbit", better: "min", fmt: (v) => Math.round(v).toLocaleString() },
  { key: "mean_latency_ms", label: "Latency ms", better: "min", fmt: (v) => num(v, 1) },
  { key: "p95_latency_ms", label: "p95 ms", better: "min", fmt: (v) => num(v, 1) },
  { key: "mean_hops", label: "Hops", better: "min", fmt: (v) => num(v, 2) },
  { key: "route_changes_per_tick", label: "Route chg/tick", better: "min", fmt: (v) => num(v, 2) },
  { key: "handoffs_total", label: "Handoffs", better: "min", fmt: (v) => num(v, 0) },
  { key: "mean_overloaded_links", label: "Overloaded", better: "min", fmt: (v) => num(v, 1) },
];

const FAILURE_COLUMNS = [
  { key: "goodput_drop", label: "Goodput drop", better: "min", fmt: (v) => pct(v, 1), failure: true },
  { key: "latency_penalty_ms", label: "Latency +ms", better: "min", fmt: (v) => num(v, 1), failure: true },
  { key: "recovery_time_s", label: "Recovery s", better: "min", fmt: (v) => num(v, 0), failure: true },
];

function mergeSeries(arms, metric) {
  const byT = new Map();
  for (const arm of arms) {
    for (const row of arm.series) {
      if (!byT.has(row.t)) byT.set(row.t, { t: row.t });
      byT.get(row.t)[arm.label] = row[metric];
    }
  }
  return [...byT.values()].sort((a, b) => a.t - b.t);
}

function bestSet(values, better) {
  const nums = values.filter((v) => typeof v === "number");
  if (nums.length < 2 || new Set(nums).size === 1) return new Set();
  const target = better === "max" ? Math.max(...nums) : Math.min(...nums);
  return new Set(values.map((v, i) => (v === target ? i : -1)).filter((i) => i >= 0));
}

export default function ExperimentResults({ detail, timelines, onReplay }) {
  const [metric, setMetric] = useState("goodput");

  if (!detail) {
    return <div className="panel"><div className="dim">Create or select an experiment.</div></div>;
  }

  const fw = detail.failure_window;
  const columns = fw ? [...COLUMNS, ...FAILURE_COLUMNS] : COLUMNS;
  const value = (arm, col) => (col.failure ? arm.summary?.failure?.[col.key] : arm.summary?.[col.key]);
  const best = columns.map((col) => bestSet(detail.arms.map((a) => value(a, col)), col.better));

  const expected = Math.floor(detail.params.duration / detail.params.dt) + 1;
  const m = METRICS.find((x) => x.key === metric);
  const rows = timelines ? mergeSeries(timelines.arms, metric) : [];
  const lastT = rows.length ? rows[rows.length - 1].t : 0;

  return (
    <>
      <div className="panel">
        <h3>
          {detail.name} <span className={`chip ${detail.status}`}>{detail.status}</span>
        </h3>
        <div className="dim">
          load ×{detail.params.load_scale} · {Math.round(detail.params.duration / 60)} min · tick {detail.params.dt} s ·
          feeders {detail.params.link_params?.ground_capacity_gbps ?? 2} Gbps ·{" "}
          {fw ? `failure ${fmtTime(fw.start)} → ${fw.end != null ? fmtTime(fw.end) : "never recovers"}` : "no failure"}
        </div>
        {detail.status === "running" && (
          <div className="hint">
            Progress: {detail.arms.map((a) => (a.status === "completed" ? "✓" : `${a.n_ticks}/${expected}`)).join(" · ")}
          </div>
        )}
      </div>

      <div className="panel">
        <div className="metric-tabs chips">
          {METRICS.map((x) => (
            <button key={x.key} className={x.key === metric ? "active" : ""} onClick={() => setMetric(x.key)}>
              {x.label}
            </button>
          ))}
        </div>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.06)" />
            <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]}
                   tickFormatter={(t) => `${Math.round(t / 60)}m`} stroke="#6b7a90" fontSize={11} />
            <YAxis domain={m.domain ?? ["auto", "auto"]} stroke="#6b7a90" fontSize={11} width={52}
                   tickFormatter={m.fmt} />
            <Tooltip contentStyle={{ background: "#111a2b", border: "1px solid #2c4160", fontSize: 12 }}
                     labelFormatter={fmtTime} formatter={(v, name) => [m.fmt(v), name]} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {fw && <ReferenceArea x1={fw.start} x2={fw.end ?? lastT} fill="#ff4d4d" fillOpacity={0.12} />}
            {(timelines?.arms ?? []).map((arm, i) => (
              <Line key={arm.run_id} type="monotone" dataKey={arm.label} stroke={COLORS[i % COLORS.length]}
                    strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
            ))}
          </LineChart>
        </ResponsiveContainer>
        {fw && <div className="hint">Shaded area: failure window.</div>}
      </div>

      <div className="panel" style={{ overflowX: "auto" }}>
        <h3>Summary <span className="hint">(green = best in column)</span></h3>
        <table className="exp-table">
          <thead>
            <tr>
              <th>Arm</th>
              {columns.map((c) => <th key={c.key}>{c.label}</th>)}
              <th />
            </tr>
          </thead>
          <tbody>
            {detail.arms.map((arm, ai) => (
              <tr key={arm.run_id}>
                <td>
                  <span className="swatch" style={{ background: COLORS[ai % COLORS.length] }} />
                  {arm.label}
                </td>
                {arm.summary
                  ? columns.map((c, ci) => {
                      const v = value(arm, c);
                      return (
                        <td key={c.key} className={best[ci].has(ai) ? "best" : ""}>
                          {v == null ? "–" : c.fmt(v)}
                        </td>
                      );
                    })
                  : <td colSpan={columns.length} className="dim">{arm.status} ({arm.n_ticks}/{expected})</td>}
                <td>
                  <button disabled={arm.status !== "completed"} onClick={() => onReplay(arm.run_id)}>Replay</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}