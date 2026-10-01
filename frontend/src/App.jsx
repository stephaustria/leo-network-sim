import { useEffect, useRef, useState } from "react";
import { API_URL } from "./config";
import Charts from "./components/Charts";
import { LiveControls, ReplayControls } from "./components/Controls";
import EventLog from "./components/EventLog";
import FlowTable from "./components/FlowTable";
import MapCanvas from "./components/MapCanvas";
import MetricsPanel from "./components/MetricsPanel";
import { useRuns } from "./hooks/useRuns";
import { useSimStream } from "./hooks/useSimStream";
import "./App.css";

export default function App() {
  const { status, init, frame, serverState, history, error, finished, open, close, send } = useSimStream();
  const { runs, create } = useRuns();

  const [mode, setMode] = useState("live");
  const [selected, setSelected] = useState(null);
  const [runId, setRunId] = useState(null);
  const [loadedRun, setLoadedRun] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [creating, setCreating] = useState(false);
  const [events, setEvents] = useState([]);
  const lastT = useRef(-1);

  // live mode keeps a socket open; replay opens one when a run is loaded
  useEffect(() => {
    if (mode === "live") open("/ws/live");
    else close();
  }, [mode, open, close]);

  // reset the event log on every new connection
  useEffect(() => {
    lastT.current = -1;
    setEvents([]);
  }, [init]);

  // append handoff/outage events from each new frame
  useEffect(() => {
    if (!frame) return;
    const reset = frame.t <= lastT.current;
    lastT.current = frame.t;
    const fresh = frame.handoffs
      .filter((h) => h.reason !== "acquired")
      .map((h) => ({ ...h, key: `${frame.t}-${h.station}-${h.reason}` }));
    setEvents((prev) => [...fresh, ...(reset ? [] : prev)].slice(0, 40));
  }, [frame]);

  const loadReplay = async () => {
    if (!runId) return;
    setSelected(null);
    setLoadedRun(runId);
    try {
      const r = await fetch(`${API_URL}/runs/${runId}/timeline`);
      setTimeline(r.ok ? await r.json() : []);
    } catch {
      setTimeline([]);
    }
    open(`/ws/replay/${runId}`);
  };

  const createRun = async (loadScale) => {
    setCreating(true);
    try {
      const id = await create({ t_start: 0, duration: 1800, dt: 60, load_scale: loadScale });
      setRunId(id);
    } catch (e) {
      alert(`Could not create run: ${e.message}`);
    } finally {
      setCreating(false);
    }
  };

  const flows = frame?.flows ?? null;
  const selectedFlow = selected != null && flows ? flows[selected] : null;
  const chartData = mode === "live" ? history : timeline;

  return (
    <div className="app">
      <header>
        <h1>LEO Network Simulator</h1>
        <div className="tabs">
          {["live", "replay"].map((m) => (
            <button key={m} className={mode === m ? "active" : ""} onClick={() => { setMode(m); setSelected(null); }}>
              {m === "live" ? "Live" : "Replay"}
            </button>
          ))}
        </div>
        <span className={`badge ${status}`}>{status}</span>
        {init && (
          <span className="dim">
            {init.constellation.n_sats} sats · {init.constellation.altitude_km} km · {init.constellation.inclination_deg}°
          </span>
        )}
      </header>

      {error && <div className="error">{error}</div>}

      <main>
        <section className="left">
          <MapCanvas init={init} frame={frame} selectedFlow={selectedFlow} />
          <Charts data={chartData} cursorT={frame?.t} />
        </section>

        <aside className="right">
          {mode === "live" ? (
            <LiveControls send={send} serverState={serverState} finished={finished} />
          ) : (
            <ReplayControls
              runs={runs} runId={runId} setRunId={setRunId} onLoad={loadReplay}
              onCreate={createRun} creating={creating} send={send}
              serverState={serverState} frame={frame} timeline={timeline}
              loaded={loadedRun != null && status === "open"}
            />
          )}
          <MetricsPanel frame={frame} />
          <FlowTable init={init} flows={flows} selected={selected} onSelect={setSelected} />
          <EventLog init={init} events={events} />
        </aside>
      </main>
    </div>
  );
}