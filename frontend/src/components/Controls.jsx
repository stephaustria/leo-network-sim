import { useState } from "react";
import { fmtTime } from "../utils";

const LOAD_STEPS = [0.1, 0.5, 1, 2, 5, 10, 20, 40, 80, 160];
const LIVE_SPEEDS = [0.5, 1, 2, 5, 10];
const REPLAY_SPEEDS = [0.5, 1, 2, 5, 10, 30];
const DT_OPTIONS = [10, 30, 60, 120, 300];

export function LiveControls({ send, serverState, finished }) {
  const [dt, setDt] = useState(60);
  const [speed, setSpeed] = useState(1);
  const [loadIdx, setLoadIdx] = useState(2);
  const started = serverState?.started;
  const paused = serverState?.paused;

  return (
    <div className="panel">
      <h3>Live simulation</h3>
      <div className="row">
        <button
          onClick={() =>
            send({ cmd: "start", t_start: 0, dt, duration: 7200, speed, load_scale: LOAD_STEPS[loadIdx] })
          }
        >
          {started ? "Restart" : "Start"}
        </button>
        <button disabled={!started} onClick={() => send({ cmd: paused ? "resume" : "pause" })}>
          {paused ? "Resume" : "Pause"}
        </button>
        <button disabled={!started} onClick={() => send({ cmd: "stop" })}>
          Stop
        </button>
      </div>
      <div className="hint">
        {finished ? "Finished." : started ? (paused ? "Paused." : "Running.") : "Press Start."}
      </div>

      <label>
        Tick step (sim seconds)
        <select
          value={dt}
          onChange={(e) => {
            const v = Number(e.target.value);
            setDt(v);
            send({ cmd: "set", dt: v });
          }}
        >
          {DT_OPTIONS.map((v) => (
            <option key={v} value={v}>{v} s</option>
          ))}
        </select>
      </label>

      <label>
        Speed (ticks per second)
        <select
          value={speed}
          onChange={(e) => {
            const v = Number(e.target.value);
            setSpeed(v);
            send({ cmd: "set", speed: v });
          }}
        >
          {LIVE_SPEEDS.map((v) => (
            <option key={v} value={v}>{v}x</option>
          ))}
        </select>
      </label>

      <label>
        Traffic load: ×{LOAD_STEPS[loadIdx]}
        <input
          type="range"
          min={0}
          max={LOAD_STEPS.length - 1}
          step={1}
          value={loadIdx}
          onChange={(e) => {
            const i = Number(e.target.value);
            setLoadIdx(i);
            send({ cmd: "set", load_scale: LOAD_STEPS[i] });
          }}
        />
      </label>
    </div>
  );
}

export function ReplayControls({
  runs, runId, setRunId, onLoad, onCreate, creating, send, serverState, frame, timeline, loaded,
}) {
  const [speed, setSpeed] = useState(1);
  const [newLoad, setNewLoad] = useState(3);
  const [dragT, setDragT] = useState(null);

  const tMin = timeline[0]?.t ?? 0;
  const tMax = timeline.length ? timeline[timeline.length - 1].t : 0;
  const step = timeline.length > 1 ? timeline[1].t - timeline[0].t : 60;
  const paused = serverState?.paused;

  const commitSeek = () => {
    if (dragT != null) {
      send({ cmd: "seek", t: dragT });
      setDragT(null);
    }
  };

  const completed = runs.filter((r) => r.status === "completed");

  return (
    <div className="panel">
      <h3>Replay stored run</h3>

      <div className="row">
        <select value={newLoad} onChange={(e) => setNewLoad(Number(e.target.value))}>
          {LOAD_STEPS.map((v) => (
            <option key={v} value={v}>load ×{v}</option>
          ))}
        </select>
        <button disabled={creating} onClick={() => onCreate(newLoad)}>
          {creating ? "Creating…" : "New 30-min run"}
        </button>
      </div>

      <div className="row">
        <select value={runId ?? ""} onChange={(e) => setRunId(Number(e.target.value))}>
          <option value="" disabled>Select a completed run</option>
          {completed.map((r) => (
            <option key={r.id} value={r.id}>
              #{r.id} · load ×{r.params.load_scale} · {r.n_ticks} ticks
            </option>
          ))}
        </select>
        <button disabled={!runId} onClick={onLoad}>Load</button>
      </div>
      {runs.some((r) => r.status === "running") && <div className="hint">A run is still computing…</div>}

      {loaded && (
        <>
          <div className="row">
            <button onClick={() => send({ cmd: paused ? "resume" : "pause" })}>
              {paused ? "Play" : "Pause"}
            </button>
            <button onClick={() => send({ cmd: "restart" })}>Restart</button>
            <select
              value={speed}
              onChange={(e) => {
                const v = Number(e.target.value);
                setSpeed(v);
                send({ cmd: "speed", speed: v });
              }}
            >
              {REPLAY_SPEEDS.map((v) => (
                <option key={v} value={v}>{v}x</option>
              ))}
            </select>
          </div>
          <label>
            {fmtTime(dragT ?? frame?.t ?? tMin)}
            <input
              type="range"
              min={tMin}
              max={tMax}
              step={step}
              value={dragT ?? frame?.t ?? tMin}
              onChange={(e) => setDragT(Number(e.target.value))}
              onPointerUp={commitSeek}
              onKeyUp={commitSeek}
            />
          </label>
        </>
      )}
    </div>
  );
}