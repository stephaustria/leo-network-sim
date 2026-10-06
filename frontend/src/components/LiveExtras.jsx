import { useState } from "react";

const POLICIES = [
  ["congestion_aware", "Congestion-aware"],
  ["shortest_latency", "Shortest latency"],
  ["min_hop", "Min hop"],
];
const STICKINESS = [0, 0.05, 0.1, 0.15, 0.25, 0.4];
const HYSTERESIS = [0, 5, 15, 30, 45, 60];

const KINDS = [
  ["plane", "Orbital plane"],
  ["satellite", "Satellite"],
  ["station", "Ground station"],
  ["seam", "Plane seam (cut links between plane N and N+1)"],
];

export function PolicyControls({ send, serverState }) {
  const policy = serverState?.policy ?? "congestion_aware";
  const stickiness = serverState?.route_stickiness ?? 0;
  const hysteresis = serverState?.hysteresis_deg ?? 15;

  return (
    <div className="panel">
      <h3>Routing and handoff <span className="hint">(applies live)</span></h3>
      <label>
        Routing policy
        <select value={policy} onChange={(e) => send({ cmd: "set", policy: e.target.value })}>
          {POLICIES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </select>
      </label>
      <label>
        Route stickiness (damps route flapping)
        <select value={stickiness}
                onChange={(e) => send({ cmd: "set", route_stickiness: Number(e.target.value) })}>
          {STICKINESS.map((v) => <option key={v} value={v}>{v === 0 ? "off" : `${v * 100}% discount`}</option>)}
        </select>
      </label>
      <label>
        Handoff hysteresis
        <select value={hysteresis}
                onChange={(e) => send({ cmd: "set", hysteresis_deg: Number(e.target.value) })}>
          {HYSTERESIS.map((v) => <option key={v} value={v}>{v}°</option>)}
        </select>
      </label>
    </div>
  );
}

export function FailurePanel({ init, frame, send, started }) {
  const [kind, setKind] = useState("plane");
  const [target, setTarget] = useState(5);
  const [duration, setDuration] = useState(0);

  const c = init?.constellation;
  const max = {
    satellite: (c?.n_sats ?? 1) - 1,
    plane: (c?.planes ?? 1) - 1,
    seam: (c?.planes ?? 1) - 1,
    station: (init?.stations?.length ?? 1) - 1,
  }[kind];

  const down = frame?.failures ?? { sats: [], stations: [], isls: [] };
  const anyDown = down.sats.length + down.stations.length + down.isls.length > 0;

  const inject = () =>
    send({ cmd: "fail", kind, target: Number(target), duration: Number(duration) || undefined });

  return (
    <div className="panel">
      <h3>Failure injection</h3>
      <label>
        What fails
        <select value={kind} onChange={(e) => { setKind(e.target.value); setTarget(0); }}>
          {KINDS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </select>
      </label>

      <label>
        {kind === "station" ? "Station" : kind === "seam" ? "Plane N" : `${kind === "plane" ? "Plane" : "Satellite"} index (0–${max})`}
        {kind === "station" ? (
          <select value={target} onChange={(e) => setTarget(Number(e.target.value))}>
            {(init?.stations ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        ) : (
          <div className="row" style={{ marginBottom: 0 }}>
            <input type="number" min={0} max={max} value={target}
                   onChange={(e) => setTarget(Math.max(0, Math.min(max, Number(e.target.value) || 0)))} />
            <button onClick={() => setTarget(Math.floor(Math.random() * (max + 1)))}>Random</button>
          </div>
        )}
      </label>

      <label>
        Duration in sim seconds (0 = until recovered)
        <input type="number" min={0} step={60} value={duration}
               onChange={(e) => setDuration(Number(e.target.value) || 0)} />
      </label>

      <div className="row" style={{ marginTop: 10 }}>
        <button disabled={!started} onClick={inject}>Inject failure</button>
        <button disabled={!started} onClick={() => send({ cmd: "recover" })}>Recover all</button>
      </div>
      {!started && <div className="hint">Start the simulation to inject failures.</div>}
      <div className="failure-summary">
        {anyDown
          ? `Down now: ${down.sats.length} satellites · ${down.stations.length} stations · ${down.isls.length} links`
          : <span className="dim">Nothing is down.</span>}
      </div>
    </div>
  );
}