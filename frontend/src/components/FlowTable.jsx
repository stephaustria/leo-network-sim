import { num, pct, stationName, utilColor } from "../utils";

export default function FlowTable({ init, flows, selected, onSelect }) {
  if (!flows) return null;
  return (
    <div className="panel">
      <h3>Flows <span className="hint">(click to show route)</span></h3>
      <table className="flows">
        <thead>
          <tr><th>Route</th><th>Latency</th><th>Loss</th><th>Util</th><th>Hops</th></tr>
        </thead>
        <tbody>
          {flows.map((f, i) => (
            <tr
              key={`${f.src}-${f.dst}`}
              className={i === selected ? "sel" : ""}
              onClick={() => onSelect(i === selected ? null : i)}
            >
              <td>{stationName(init, f.src)} → {stationName(init, f.dst)}</td>
              {f.reachable ? (
                <>
                  <td>{num(f.latency_ms)} ms</td>
                  <td>{pct(f.loss, 2)}</td>
                  <td style={{ color: utilColor(f.max_util) }}>{pct(f.max_util, 0)}</td>
                  <td>{f.hops}</td>
                </>
              ) : (
                <td colSpan={4} className="dim">no route</td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}