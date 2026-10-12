import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { num, pct } from "../utils";

export function LatitudeChart({ data }) {
  return (
    <div className="panel">
      <h3>Latitude profile</h3>
      <ResponsiveContainer width="100%" height={210}>
        <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.06)" />
          <XAxis dataKey="lat" type="number" domain={[-90, 90]} ticks={[-90, -60, -30, 0, 30, 60, 90]}
                 tickFormatter={(v) => `${v}°`} stroke="#6b7a90" fontSize={11} />
          <YAxis yAxisId="a" domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`}
                 stroke="#6b7a90" fontSize={11} width={44} />
          <YAxis yAxisId="v" orientation="right" stroke="#6b7a90" fontSize={11} width={36} />
          <Tooltip contentStyle={{ background: "#111a2b", border: "1px solid #2c4160", fontSize: 12 }}
                   labelFormatter={(v) => `latitude ${v}°`} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line yAxisId="a" dataKey="availability" name="Availability" stroke="#6ee7a8"
                strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line yAxisId="v" dataKey="mean_visible" name="Satellites in view" stroke="#ffb454"
                strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function StationTable({ stations }) {
  return (
    <div className="panel" style={{ overflowX: "auto" }}>
      <h3>Ground stations</h3>
      <table className="exp-table">
        <thead>
          <tr>
            <th>Station</th><th>Availability</th><th>In view</th>
            <th>Latency</th><th>p95</th><th>Longest gap</th>
          </tr>
        </thead>
        <tbody>
          {stations.map((s) => (
            <tr key={s.name}>
              <td>{s.name}</td>
              <td>{pct(s.availability, 1)}</td>
              <td>{num(s.mean_visible, 1)}</td>
              <td>{s.mean_latency_ms == null ? "–" : `${num(s.mean_latency_ms, 1)} ms`}</td>
              <td>{s.p95_latency_ms == null ? "–" : `${num(s.p95_latency_ms, 1)} ms`}</td>
              <td>{num(s.longest_gap_min, 0)} min</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}