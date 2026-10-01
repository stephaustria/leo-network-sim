import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { fmtTime } from "../utils";

function MiniChart({ title, data, dataKey, color, cursorT, domain, format }) {
  return (
    <div className="chart">
      <div className="chart-title">{title}</div>
      <ResponsiveContainer width="100%" height={120}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.06)" />
          <XAxis
            dataKey="t" type="number" domain={["dataMin", "dataMax"]}
            tickFormatter={(t) => `${Math.round(t / 60)}m`} stroke="#6b7a90" fontSize={10}
          />
          <YAxis domain={domain} stroke="#6b7a90" fontSize={10} width={44} tickFormatter={format} />
          <Tooltip
            contentStyle={{ background: "#111a2b", border: "1px solid #2c4160", fontSize: 12 }}
            labelFormatter={fmtTime}
            formatter={(v) => [format(v), title]}
          />
          <Line type="monotone" dataKey={dataKey} stroke={color} dot={false}
                isAnimationActive={false} connectNulls />
          {cursorT != null && <ReferenceLine x={cursorT} stroke="#fff" strokeDasharray="3 3" />}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function Charts({ data, cursorT }) {
  return (
    <div className="charts">
      <MiniChart title="Delivery ratio" data={data} dataKey="delivery_ratio" color="#6ee7a8"
                 cursorT={cursorT} domain={[0, 1]} format={(v) => `${(v * 100).toFixed(0)}%`} />
      <MiniChart title="Mean latency" data={data} dataKey="mean_latency_ms" color="#7aa2f7"
                 cursorT={cursorT} domain={["auto", "auto"]} format={(v) => `${Number(v).toFixed(0)} ms`} />
      <MiniChart title="Max link utilization" data={data} dataKey="max_link_util" color="#ffb454"
                 cursorT={cursorT} domain={[0, "auto"]} format={(v) => `${(v * 100).toFixed(0)}%`} />
    </div>
  );
}