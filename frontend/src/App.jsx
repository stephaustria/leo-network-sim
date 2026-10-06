import { useCallback, useEffect, useRef, useState } from "react";
import { API_URL } from "./config";
import Charts from "./components/Charts";
import { LiveControls, ReplayControls } from "./components/Controls";
import EventLog from "./components/EventLog";
import ExperimentForm from "./components/ExperimentForm";
import ExperimentList from "./components/ExperimentList";
import ExperimentResults from "./components/ExperimentResults";
import FlowTable from "./components/FlowTable";
import { FailurePanel, PolicyControls } from "./components/LiveExtras";
import MapCanvas from "./components/MapCanvas";
import MetricsPanel from "./components/MetricsPanel";
import { useExperiments } from "./hooks/useExperiments";
import { useRuns } from "./hooks/useRuns";
import { useSimStream } from "./hooks/useSimStream";
import "./App.css";

const MODES = [["live", "Live"], ["replay", "Replay"], ["experiments", "Experiments"]];

export default function App() {
  const { status, init, frame, serverState, history, error, finished, open, close, send } = useSimStream();
  const { runs, create } = useRuns();
  const exp = useExperiments();

  const [mode, setMode] = useState("live");
  const [selected, setSelected] = useState(null);
  const [runId, setRunId] = useState(null);
  const [loadedRun, setLoadedRun] = useState(null);
  const [pendingReplay, setPendingReplay] = useState(null);
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

  const loadReplay = useCallback(async (id) => {
    if (!id) return;
    setSelected(null);
    setLoadedRun(id);
    try {
      const r = await fetch(`${API_URL}/runs/${id}/timeline`);
      setTimeline(r.ok ? await r.json() : []);
    } catch {
      setTimeline([]);
    }
    open(`/ws/replay/${id}`);
  }, [open]);

  // "Replay" button in the experiment table: switch tabs, then load that run
  useEffect(() => {
    if (mode === "replay" && pendingReplay != null) {
      loadReplay(pendingReplay);
      setPendingReplay(null);
    }
  }, [mode, pendingReplay, loadReplay]);

  const replayRun = (id) => {
    setRunId(id);
    setPendingReplay(id);
    setMode("replay");
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
          {MODES.map(([m, label]) => (
            <button key={m} className={mode === m ? "active" : ""}
                    onClick={() => { setMode(m); setSelected(null); }}>
              {label}
            </button>
          ))}
        </div>
        {mode !== "experiments" && <span className={`badge ${status}`}>{status}</span>}
        {mode !== "experiments" && init && (
          <span className="dim">
            {init.constellation.n_sats} sats · {init.constellation.altitude_km} km · {init.constellation.inclination_deg}°
          </span>
        )}
      </header>

      {error && mode !== "experiments" && <div className="error">{error}</div>}

      {mode === "experiments" ? (
        <main>
          <section className="left">
            <ExperimentResults detail={exp.detail} timelines={exp.timelines} onReplay={replayRun} />
          </section>
          <aside className="right">
            <ExperimentForm onSubmit={exp.create} />
            <ExperimentList list={exp.list} selectedId={exp.selectedId}
                            onSelect={exp.select} onDelete={exp.remove} />
          </aside>
        </main>
      ) : (
        <main>
          <section className="left">
            <MapCanvas init={init} frame={frame} selectedFlow={selectedFlow} />
            <Charts data={chartData} cursorT={frame?.t} />
          </section>

          <aside className="right">
            {mode === "live" ? (
              <>
                <LiveControls send={send} serverState={serverState} finished={finished} />
                <PolicyControls send={send} serverState={serverState} />
                <FailurePanel init={init} frame={frame} send={send} started={!!serverState?.started} />
              </>
            ) : (
              <ReplayControls
                runs={runs} runId={runId} setRunId={setRunId} onLoad={() => loadReplay(runId)}
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
      )}
    </div>
  );
}