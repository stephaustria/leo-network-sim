import { SHELL_COLORS } from "./shells";

const LINK_FIELDS = [
  ["ground_capacity_gbps", "Ground link capacity (Gbps)", 2],
  ["isl_capacity_gbps", "ISL capacity (Gbps)", 10],
  ["min_elevation_deg", "Min elevation (°)", 25],
  ["max_isl_range_km", "Max ISL range (km)", 5000],
];

const DEFAULT_SHELL = { altitude_km: 550, inclination_deg: 53, planes: 24, sats_per_plane: 22, phasing: 1 };
const NEW_EXTRA_SHELL = { altitude_km: 1100, inclination_deg: 87, planes: 8, sats_per_plane: 12, phasing: 1 };
const DEFAULT_ISL = { mode: "auto", max_degree: 4, inter_shell_degree: 0, replan_s: 300 };
const ISL_MODES = [
  ["auto", "Auto: grid for Walker shells, nearest neighbours for TLE"],
  ["grid", "Grid (Walker shells only)"],
  ["nearest", "Nearest neighbours (all shells)"],
  ["none", "None (bent pipe only)"],
];

function NumField({ label, value, onChange, min, max, step = 1, placeholder }) {
  return (
    <label>
      {label}
      <input type="number" value={value ?? ""} min={min} max={max} step={step}
             placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

const toNumber = (raw) => (raw === "" ? 0 : Number(raw));

function WalkerFields({ title, shell, onChange, onRemove }) {
  const set = (key, raw) => onChange({ ...shell, [key]: toNumber(raw) });
  return (
    <div className="shell-box">
      <div className="shell-head">
        <b>{title}</b>
        {onRemove && <button onClick={onRemove}>Remove</button>}
      </div>
      <div className="field-grid">
        <NumField label="Altitude (km)" value={shell.altitude_km} min={300} max={2000} step={10}
                  onChange={(v) => set("altitude_km", v)} />
        <NumField label="Inclination (°)" value={shell.inclination_deg} min={0} max={100}
                  onChange={(v) => set("inclination_deg", v)} />
        <NumField label="Planes" value={shell.planes} min={3} max={72} onChange={(v) => set("planes", v)} />
        <NumField label="Satellites per plane" value={shell.sats_per_plane} min={3} max={72}
                  onChange={(v) => set("sats_per_plane", v)} />
        <NumField label="Phasing (F)" value={shell.phasing} min={0} max={Math.max(0, shell.planes - 1)}
                  onChange={(v) => set("phasing", v)} />
        <div className="dim" style={{ alignSelf: "end", paddingBottom: 6 }}>
          {shell.planes * shell.sats_per_plane} satellites
        </div>
      </div>
    </div>
  );
}

export default function ScenarioEditor({
  draft, setDraft, preview, tleSets = [], isSaved, isDefault, saving, error,
  addMode, setAddMode, onSave, onSaveNew, onDelete,
}) {
  if (!draft) return <div className="panel"><div className="dim">Loading…</div></div>;

  const cfg = draft.config;
  const extra = cfg.extra_shells ?? [];
  const tleShells = cfg.tle_shells ?? [];
  const isl = { ...DEFAULT_ISL, ...(cfg.isl ?? {}) };
  const walkerShells = (cfg.constellation ? 1 : 0) + extra.length;

  const setCfg = (fn) => setDraft((d) => ({ ...d, config: fn(d.config) }));
  const setExtra = (i, shell) =>
    setCfg((x) => ({ ...x, extra_shells: (x.extra_shells ?? []).map((s, k) => (k === i ? shell : s)) }));
  const setTle = (i, patch) =>
    setCfg((x) => ({ ...x, tle_shells: (x.tle_shells ?? []).map((t, k) => (k === i ? { ...t, ...patch } : t)) }));
  const setIsl = (key, raw) =>
    setCfg((x) => ({ ...x, isl: { ...DEFAULT_ISL, ...(x.isl ?? {}), [key]: key === "mode" ? raw : toNumber(raw) } }));
  const setStation = (i, patch) =>
    setCfg((x) => ({ ...x, stations: x.stations.map((s, k) => (k === i ? { ...s, ...patch } : s)) }));
  const setLink = (key, raw) =>
    setCfg((x) => {
      const link_params = { ...x.link_params };
      if (raw === "") delete link_params[key];
      else link_params[key] = Number(raw);
      return { ...x, link_params };
    });

  const s = preview.summary;

  return (
    <div className="panel">
      <h3>{isDefault ? "Editing a copy of the default" : "Scenario"}</h3>

      <label>
        Name
        <input type="text" value={draft.name} maxLength={80}
               onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
      </label>
      <label>
        Description
        <input type="text" value={draft.description} maxLength={500}
               onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))} />
      </label>

      <h3 style={{ marginTop: 14 }}>Walker shells</h3>
      <label className="check">
        <input type="checkbox" checked={!!cfg.constellation}
               disabled={!!cfg.constellation && tleShells.length === 0}
               onChange={(e) => setCfg((x) => ({ ...x, constellation: e.target.checked ? { ...DEFAULT_SHELL } : null }))} />
        Walker shell 1 {tleShells.length === 0 && "(needed unless the scenario has TLE shells)"}
      </label>
      {cfg.constellation && (
        <WalkerFields title="Walker shell 1" shell={cfg.constellation}
                      onChange={(shell) => setCfg((x) => ({ ...x, constellation: shell }))} />
      )}
      {extra.map((shell, i) => (
        <WalkerFields key={i} title={`Walker shell ${i + 2}`} shell={shell} onChange={(sh) => setExtra(i, sh)}
                      onRemove={() => setCfg((x) => ({
                        ...x, extra_shells: (x.extra_shells ?? []).filter((_, k) => k !== i),
                      }))} />
      ))}
      <button disabled={extra.length >= 3}
              onClick={() => setCfg((x) => ({ ...x, extra_shells: [...(x.extra_shells ?? []), { ...NEW_EXTRA_SHELL }] }))}>
        + Add Walker shell
      </button>

      <h3 style={{ marginTop: 14 }}>Real satellites (TLE shells)</h3>
      {tleShells.map((t, i) => (
        <div className="shell-box" key={i}>
          <div className="shell-head">
            <b>TLE shell {i + 1}</b>
            <button onClick={() => setCfg((x) => ({
              ...x, tle_shells: (x.tle_shells ?? []).filter((_, k) => k !== i),
            }))}>Remove</button>
          </div>
          <label>
            TLE set
            <select value={t.tle_set_id} onChange={(e) => setTle(i, { tle_set_id: Number(e.target.value) })}>
              {tleSets.map((set) => (
                <option key={set.id} value={set.id}>
                  {set.name} · {set.n_sats} sats · {String(set.epoch).slice(0, 10)}
                </option>
              ))}
              {!tleSets.some((set) => set.id === t.tle_set_id) && <option value={t.tle_set_id}>#{t.tle_set_id}</option>}
            </select>
          </label>
          <div className="field-grid">
            <NumField label="Max satellites (empty = all)" value={t.limit} min={1} max={1600}
                      onChange={(v) => setTle(i, { limit: v === "" ? null : Number(v) })} />
            <label>
              Name contains
              <input type="text" value={t.name_contains ?? ""} maxLength={40}
                     onChange={(e) => setTle(i, { name_contains: e.target.value || null })} />
            </label>
          </div>
        </div>
      ))}
      <button disabled={tleShells.length >= 3 || tleSets.length === 0}
              onClick={() => setCfg((x) => ({
                ...x, tle_shells: [...(x.tle_shells ?? []),
                  { tle_set_id: tleSets[0].id, limit: null, name_contains: null }],
              }))}>
        + Add TLE shell
      </button>
      {tleSets.length === 0 && <div className="hint">Add a TLE set in the panel above first.</div>}

      <label>
        Simulation start (epoch, UTC)
        <div className="row" style={{ marginBottom: 0 }}>
          <input type="text" value={cfg.epoch ?? ""} placeholder="empty = TLE epoch"
                 onChange={(e) => setCfg((x) => ({ ...x, epoch: e.target.value.trim() === "" ? null : e.target.value }))} />
          <button onClick={() => setCfg((x) => ({ ...x, epoch: `${new Date().toISOString().slice(0, 19)}Z` }))}>Now</button>
        </div>
      </label>
      <div className="hint">
        Real orbits start at this time (default: the TLE epoch). Walker-only scenarios without an epoch use a
        simplified Earth rotation. Format: 2026-10-13T00:00:00Z.
      </div>

      <div className="summary-box">
        {preview.error && <div className="warn">{preview.error}</div>}
        {s && (
          <>
            <div className="summary-grid">
              <span>Satellites</span><b>{s.n_sats}</b>
              <span>Stations / flows</span><b>{s.n_stations} / {s.n_flows}</b>
              {s.period_min != null && (<><span>First shell period</span><b>{s.period_min} min</b></>)}
              {s.footprint_radius_km != null && (<><span>First shell footprint</span><b>{s.footprint_radius_km} km</b></>)}
              <span>Mean in view (est.)</span><b>{s.mean_sats_in_view_estimate}</b>
            </div>
            {(s.shells ?? []).map((sh, i) => (
              <div className="shell-line" key={i}>
                <span className="dot" style={{ background: SHELL_COLORS[i % SHELL_COLORS.length] }} />
                {sh.kind === "tle" ? `TLE · ${sh.name}` : `Walker ${i + 1}`}: {sh.n_sats} sats,{" "}
                {sh.altitude_km} km, {sh.inclination_deg}°, {sh.period_min} min
                {sh.dropped ? ` (${sh.dropped} could not be propagated)` : ""}
              </div>
            ))}
            {!s.intra_plane_links_in_range && (
              <div className="warn">
                Neighbors in a plane are farther apart than the {s.max_isl_range_km} km ISL range, so intra-plane
                links will be down. Raise the max ISL range or add satellites per plane.
              </div>
            )}
          </>
        )}
      </div>

      <h3 style={{ marginTop: 14 }}>Inter-satellite links</h3>
      <label>
        Topology
        <select value={isl.mode} onChange={(e) => setIsl("mode", e.target.value)}>
          {ISL_MODES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </select>
      </label>
      <div className="field-grid">
        <NumField label="Links per satellite" value={isl.max_degree} min={1} max={8}
                  onChange={(v) => setIsl("max_degree", v)} />
        <NumField label="Inter-shell links" value={isl.inter_shell_degree} min={0} max={2}
                  onChange={(v) => setIsl("inter_shell_degree", v)} />
        <NumField label="Replan every (s, 0 = each tick)" value={isl.replan_s} min={0} max={3600} step={60}
                  onChange={(v) => setIsl("replan_s", v)} />
      </div>
      {isl.inter_shell_degree > 0 && walkerShells < 2 && (
        <div className="hint">Inter-shell links need at least two Walker shells.</div>
      )}

      <h3 style={{ marginTop: 14 }}>Link parameters <span className="hint">(empty = default)</span></h3>
      <div className="field-grid">
        {LINK_FIELDS.map(([key, label, def]) => (
          <NumField key={key} label={label} value={cfg.link_params[key]} placeholder={String(def)}
                    step={key === "max_isl_range_km" ? 100 : 1} onChange={(v) => setLink(key, v)} />
        ))}
        <NumField label="Flow demand per pair (Gbps)" value={cfg.flow_demand_gbps} step={0.05}
                  onChange={(v) => setCfg((x) => ({ ...x, flow_demand_gbps: toNumber(v) }))} />
      </div>

      <h3 style={{ marginTop: 14 }}>Ground stations</h3>
      {cfg.stations.map((st, i) => (
        <div className="station-row" key={i}>
          <input type="text" value={st.name} maxLength={40} onChange={(e) => setStation(i, { name: e.target.value })} />
          <input type="number" value={st.lat} min={-90} max={90} step={0.1}
                 onChange={(e) => setStation(i, { lat: toNumber(e.target.value) })} />
          <input type="number" value={st.lon} min={-180} max={180} step={0.1}
                 onChange={(e) => setStation(i, { lon: toNumber(e.target.value) })} />
          <button disabled={cfg.stations.length <= 2}
                  onClick={() => setCfg((x) => ({ ...x, stations: x.stations.filter((_, k) => k !== i) }))}>✕</button>
        </div>
      ))}
      <div className="row">
        <button disabled={cfg.stations.length >= 20}
                onClick={() => setCfg((x) => ({
                  ...x, stations: [...x.stations, { name: `Station ${x.stations.length + 1}`, lat: 0, lon: 0 }],
                }))}>
          + Add station
        </button>
        <button className={addMode ? "active" : ""} onClick={() => setAddMode(!addMode)}>
          {addMode ? "Click the map… (cancel)" : "Add by clicking the map"}
        </button>
      </div>

      {error && <div className="warn">{error}</div>}
      <div className="row" style={{ marginTop: 12 }}>
        {isSaved && <button disabled={saving} onClick={onSave}>Save changes</button>}
        <button disabled={saving} onClick={onSaveNew}>{isSaved ? "Save as new" : "Save as new scenario"}</button>
        {isSaved && <button disabled={saving} onClick={onDelete}>Delete</button>}
      </div>
    </div>
  );
}