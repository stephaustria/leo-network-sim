import { useEffect, useMemo, useState } from "react";
import { API_URL } from "../config";
import { useCoverage } from "../hooks/useCoverage";
import { num, pct, readError } from "../utils";
import { LatitudeChart, StationTable } from "./CoveragePanels";
import HeatLegend from "./HeatLegend";
import MapCanvas from "./MapCanvas";
import ScenarioEditor from "./ScenarioEditor";
import { HEAT_METRICS, makeHeatmap } from "./heat";

const RESOLUTIONS = [10, 5, 3, 2];
const WINDOWS = [6, 12, 24];
const STEPS = [120, 180, 300];
const clone = (x) => JSON.parse(JSON.stringify(x));

export default function ScenariosTab({ scenarios, activeScenarioId, onUse, onDeleted }) {
  const [selected, setSelected] = useState("default");        // "default" or a scenario id
  const [draft, setDraft] = useState(null);                    // { name, description, config }
  const [preview, setPreview] = useState({ summary: null, error: null });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [addMode, setAddMode] = useState(false);
  const [metric, setMetric] = useState("availability");
  const [hover, setHover] = useState(null);
  const [params, setParams] = useState({ res_deg: 5, window_hours: 12, step_s: 180 });
  const [coveredKey, setCoveredKey] = useState(null);
  const coverage = useCoverage();
  const { defaultScenario, load } = scenarios;

  // load the selected scenario into the editor
  useEffect(() => {
    let cancelled = false;
    setSaveError(null);
    coverage.clear();
    setCoveredKey(null);
    (async () => {
      if (selected === "default") {
        if (defaultScenario) {
          setDraft({ name: "My scenario", description: "", config: clone(defaultScenario.config) });
        }
      } else {
        const s = await load(selected);
        if (!cancelled && s) {
          setDraft({ name: s.name, description: s.description ?? "", config: s.config });
        }
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, defaultScenario, load]);

  // live analytic summary of the draft (debounced)
  useEffect(() => {
    if (!draft) return undefined;
    const handle = setTimeout(async () => {
      try {
        const r = await fetch(`${API_URL}/scenarios/preview`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ config: draft.config }),
        });
        if (r.ok) setPreview({ summary: (await r.json()).summary, error: null });
        else setPreview({ summary: null, error: await readError(r) });
      } catch {
        setPreview({ summary: null, error: "Backend not reachable" });
      }
    }, 400);
    return () => clearTimeout(handle);
  }, [draft?.config]); // eslint-disable-line react-hooks/exhaustive-deps

  const configKey = draft ? JSON.stringify(draft.config) : null;
  const stale = coverage.data && coveredKey !== configKey;
  const heatmap = useMemo(() => makeHeatmap(coverage.data, metric, 0.85), [coverage.data, metric]);
  const isSaved = selected !== "default";

  const computeCoverage = () => {
    setCoveredKey(configKey);
    coverage.compute({ config: draft.config, params });
  };

  const addStationAt = ({ lat, lon }) =>
    setDraft((d) => {
      if (d.config.stations.length >= 20) return d;
      const station = { name: `Station ${d.config.stations.length + 1}`,
                        lat: Math.round(lat * 100) / 100, lon: Math.round(lon * 100) / 100 };
      return { ...d, config: { ...d.config, stations: [...d.config.stations, station] } };
    });

  const save = async (asNew) => {
    setSaving(true);
    setSaveError(null);
    try {
      const body = { name: draft.name, description: draft.description || null, config: draft.config };
      const saved = await scenarios.save(asNew || !isSaved ? null : selected, body);
      setSelected(saved.id);
    } catch (e) {
      setSaveError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!isSaved || !window.confirm(`Delete scenario "${draft.name}"? Runs that used it keep their own copy.`)) return;
    const id = selected;
    await scenarios.remove(id);
    onDeleted(id);
    setSelected("default");
  };

  const s = coverage.data?.summary;
  const metricDef = HEAT_METRICS.find((m) => m.key === metric);
  const inUse = (selected === "default" ? null : selected) === activeScenarioId;

  return (
    <main>
      <section className="left">
        <div className="panel">
          <div className="metric-tabs chips">
            {HEAT_METRICS.map((m) => (
              <button key={m.key} className={m.key === metric ? "active" : ""} onClick={() => setMetric(m.key)}>
                {m.label}
              </button>
            ))}
          </div>
          <div className="hover-readout">
            {hover
              ? `${hover.lat.toFixed(1)}°, ${hover.lon.toFixed(1)}°${
                  heatmap ? ` · ${metricDef.label}: ${hover.value == null ? "no coverage" : metricDef.fmt(hover.value)}` : ""}`
              : heatmap ? "Hover the map to read values" : "Compute coverage to see the heatmap"}
          </div>
        </div>

        <MapCanvas heatmap={heatmap} stations={draft?.config.stations}
                   onHover={setHover} onMapClick={addMode ? addStationAt : undefined} />
        <HeatLegend heatmap={heatmap} />
        {stale && <div className="warn">The scenario changed since this heatmap was computed. Compute again to refresh it.</div>}
        {coverage.error && <div className="error">{coverage.error}</div>}

        {coverage.data && (
          <>
            <div className="panel">
              <div className="cards">
                {[
                  ["Global availability", pct(s.global_availability, 1)],
                  ["Mean satellites in view", num(s.global_mean_visible, 2)],
                  ["Mean access latency", s.mean_access_latency_ms == null ? "–" : `${num(s.mean_access_latency_ms, 1)} ms`],
                  ["Area with ≥99% availability", `${num(s.area_pct_availability_ge_99, 1)}%`],
                  ["Area with any coverage", `${num(s.area_pct_with_any_coverage, 1)}%`],
                  ["Worst outage", `${num(s.worst_gap_min, 0)} min`],
                ].map(([label, value]) => (
                  <div className="card" key={label}>
                    <div className="card-label">{label}</div>
                    <div className="card-value">{value}</div>
                  </div>
                ))}
              </div>
              <div className="hint">
                {coverage.data.params.n_sats} satellites · {coverage.data.params.window_hours} h window ·
                computed in {coverage.data.elapsed_s} s
              </div>
            </div>
            <LatitudeChart data={coverage.data.by_latitude} />
            <StationTable stations={coverage.data.stations} />
          </>
        )}
      </section>

      <aside className="right">
        <div className="panel">
          <h3>Scenarios</h3>
          <select value={selected} onChange={(e) => setSelected(e.target.value === "default" ? "default" : Number(e.target.value))}>
            <option value="default">Default (built-in)</option>
            {scenarios.list.map((sc) => (
              <option key={sc.id} value={sc.id}>{sc.name} · {sc.n_sats} sats</option>
            ))}
          </select>
          <div className="row" style={{ marginTop: 10 }}>
            <button disabled={inUse} onClick={() => onUse(selected === "default" ? null : selected)}>
              {inUse ? "✓ In use for simulations" : "Use for simulations"}
            </button>
          </div>
        </div>

        <div className="panel">
          <h3>Coverage</h3>
          <div className="row" style={{ marginBottom: 0 }}>
            <select value={params.res_deg} onChange={(e) => setParams((p) => ({ ...p, res_deg: Number(e.target.value) }))}>
              {RESOLUTIONS.map((v) => <option key={v} value={v}>{v}° grid</option>)}
            </select>
            <select value={params.window_hours} onChange={(e) => setParams((p) => ({ ...p, window_hours: Number(e.target.value) }))}>
              {WINDOWS.map((v) => <option key={v} value={v}>{v} h</option>)}
            </select>
            <select value={params.step_s} onChange={(e) => setParams((p) => ({ ...p, step_s: Number(e.target.value) }))}>
              {STEPS.map((v) => <option key={v} value={v}>{v} s step</option>)}
            </select>
          </div>
          <div style={{ marginTop: 10 }}>
            <button disabled={!draft || coverage.loading || !!preview.error} onClick={computeCoverage}>
              {coverage.loading ? "Computing…" : "Compute coverage"}
            </button>
          </div>
          <div className="hint">Computes for the scenario as currently edited, saved or not.</div>
        </div>

        <ScenarioEditor
          draft={draft} setDraft={setDraft} preview={preview}
          isSaved={isSaved} isDefault={!isSaved} saving={saving} error={saveError}
          addMode={addMode} setAddMode={setAddMode}
          onSave={() => save(false)} onSaveNew={() => save(true)} onDelete={remove}
        />
      </aside>
    </main>
  );
}