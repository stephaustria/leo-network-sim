import { num, pct } from "../utils";
import { HEAT_METRICS } from "./heat";

export default function CoverageOverlay({ overlay, setOverlay, state }) {
  const s = state.data?.summary;
  return (
    <div className="panel">
      <h3>Coverage overlay</h3>
      <label className="check">
        <input type="checkbox" checked={overlay.enabled}
               onChange={(e) => setOverlay((o) => ({ ...o, enabled: e.target.checked }))} />
        Show coverage heatmap under the satellites
      </label>
      {overlay.enabled && (
        <>
          <label>
            Metric
            <select value={overlay.metric}
                    onChange={(e) => setOverlay((o) => ({ ...o, metric: e.target.value }))}>
              {HEAT_METRICS.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
            </select>
          </label>
          {state.loading && <div className="hint">Computing coverage (a few seconds the first time)…</div>}
          {state.error && <div className="warn">{state.error}</div>}
          {s && (
            <div className="hint">
              Global availability {pct(s.global_availability, 1)} · mean in view {num(s.global_mean_visible, 1)}
            </div>
          )}
        </>
      )}
    </div>
  );
}