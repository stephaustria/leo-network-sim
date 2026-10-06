import { useRef, useState } from "react";

const PRESETS = [
  ["none", "No failure"],
  ["plane_outage", "Plane outage (plane 5)"],
  ["adjacent_planes", "Two adjacent planes down (5 and 6)"],
  ["station_loss", "Ground station down (first station)"],
  ["plane_seam_cut", "Plane seam cut (links between planes 5 and 6)"],
];
const LOADS = [0.5, 1, 2, 5, 10, 20, 40, 80];
const POLICY_OPTIONS = [
  ["congestion_aware", "congestion-aware"],
  ["shortest_latency", "shortest-latency"],
  ["min_hop", "min-hop"],
];
const STICKINESS = [0, 0.05, 0.1, 0.15, 0.25, 0.4];
const HYSTERESIS = [0, 5, 15, 30, 45, 60];
const MAX_TICKS = 120;

// [policy, stickiness, hysteresis]
const ARM_PRESETS = {
  "3 policies": () => [["congestion_aware", 0, 15], ["shortest_latency", 0, 15], ["min_hop", 0, 15]],
  "Stickiness": () => [["congestion_aware", 0, 15], ["congestion_aware", 0.15, 15],
                       ["min_hop", 0, 15], ["min_hop", 0.15, 15]],
  "Hysteresis sweep": () => [0, 5, 15, 30, 45].map((h) => ["min_hop", 0, h]),
};

export default function ExperimentForm({ onSubmit }) {
  const counter = useRef(0);
  const makeArm = ([policy, stickiness, hysteresis]) => ({ id: counter.current++, policy, stickiness, hysteresis });

  const [name, setName] = useState("my experiment");
  const [preset, setPreset] = useState("plane_outage");
  const [load, setLoad] = useState(20);
  const [minutes, setMinutes] = useState(30);
  const [dt, setDt] = useState(60);
  const [feeder, setFeeder] = useState("high");
  const [arms, setArms] = useState(() => ARM_PRESETS["3 policies"]().map(makeArm));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const steps = Math.floor((minutes * 60) / dt);
  const tooMany = steps > MAX_TICKS;
  const canRun = !busy && !tooMany && arms.length >= 2 && arms.length <= 6;
  const estimate = Math.round((steps + 1) * arms.length * 0.5);

  const updateArm = (id, patch) => setArms((a) => a.map((x) => (x.id === id ? { ...x, ...patch } : x)));

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await onSubmit({
        name, preset, load_scale: load, duration: minutes * 60, dt,
        link_params: feeder === "high" ? { ground_capacity_gbps: 100 } : {},
        arms: arms.map((a) => ({ policy: a.policy, route_stickiness: a.stickiness, hysteresis_deg: a.hysteresis })),
      });
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel">
      <h3>New experiment</h3>
      <label>
        Name
        <input type="text" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
      </label>
      <label>
        Failure scenario
        <select value={preset} onChange={(e) => setPreset(e.target.value)}>
          {PRESETS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </select>
      </label>
      <label>
        Traffic load: ×{load}
        <select value={load} onChange={(e) => setLoad(Number(e.target.value))}>
          {LOADS.map((v) => <option key={v} value={v}>×{v}</option>)}
        </select>
      </label>
      <div className="row" style={{ marginTop: 10 }}>
        <label style={{ flex: 1, marginTop: 0 }}>
          Duration
          <select value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}>
            {[15, 30, 60].map((v) => <option key={v} value={v}>{v} min</option>)}
          </select>
        </label>
        <label style={{ flex: 1, marginTop: 0 }}>
          Tick step
          <select value={dt} onChange={(e) => setDt(Number(e.target.value))}>
            {[30, 60, 120].map((v) => <option key={v} value={v}>{v} s</option>)}
          </select>
        </label>
      </div>
      <label>
        Ground feeder capacity
        <select value={feeder} onChange={(e) => setFeeder(e.target.value)}>
          <option value="high">High (100 Gbps): the ISL mesh is the bottleneck</option>
          <option value="standard">Standard (2 Gbps): ground links are the bottleneck</option>
        </select>
      </label>

      <h3 style={{ marginTop: 14 }}>Arms</h3>
      <div className="chips">
        {Object.keys(ARM_PRESETS).map((k) => (
          <button key={k} onClick={() => setArms(ARM_PRESETS[k]().map(makeArm))}>{k}</button>
        ))}
      </div>
      {arms.map((a) => (
        <div className="arm-row" key={a.id}>
          <select value={a.policy} onChange={(e) => updateArm(a.id, { policy: e.target.value })}>
            {POLICY_OPTIONS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
          </select>
          <select value={a.stickiness} title="route stickiness"
                  onChange={(e) => updateArm(a.id, { stickiness: Number(e.target.value) })}>
            {STICKINESS.map((v) => <option key={v} value={v}>{v === 0 ? "no stick" : `stick ${v}`}</option>)}
          </select>
          <select value={a.hysteresis} title="handoff hysteresis"
                  onChange={(e) => updateArm(a.id, { hysteresis: Number(e.target.value) })}>
            {HYSTERESIS.map((v) => <option key={v} value={v}>hyst {v}°</option>)}
          </select>
          <button disabled={arms.length <= 2} onClick={() => setArms((x) => x.filter((y) => y.id !== a.id))}>✕</button>
        </div>
      ))}
      <button disabled={arms.length >= 6}
              onClick={() => setArms((x) => [...x, makeArm(["congestion_aware", 0, 15])])}>
        + Add arm
      </button>

      <div style={{ marginTop: 12 }}>
        <button disabled={!canRun} onClick={submit}>{busy ? "Starting…" : "Run experiment"}</button>
      </div>
      {tooMany
        ? <div className="warn">Too many ticks ({steps}; max {MAX_TICKS}). Raise the tick step or shorten the run.</div>
        : <div className="hint">{steps + 1} ticks × {arms.length} arms, roughly {estimate} s of compute.</div>}
      {error && <div className="warn">{error}</div>}
    </div>
  );
}