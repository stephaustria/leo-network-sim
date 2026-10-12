const LINK_FIELDS = [
  ["ground_capacity_gbps", "Ground link capacity (Gbps)", 2],
  ["isl_capacity_gbps", "ISL capacity (Gbps)", 10],
  ["min_elevation_deg", "Min elevation (°)", 25],
  ["max_isl_range_km", "Max ISL range (km)", 5000],
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

export default function ScenarioEditor({
  draft, setDraft, preview, isSaved, isDefault, saving, error,
  addMode, setAddMode, onSave, onSaveNew, onDelete,
}) {
  if (!draft) return <div className="panel"><div className="dim">Loading…</div></div>;

  const cfg = draft.config;
  const c = cfg.constellation;
  const setCfg = (fn) => setDraft((d) => ({ ...d, config: fn(d.config) }));
  const setC = (key, raw) => setCfg((x) => ({ ...x, constellation: { ...x.constellation, [key]: toNumber(raw) } }));
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

      <h3 style={{ marginTop: 14 }}>Constellation (Walker Delta)</h3>
      <div className="field-grid">
        <NumField label="Altitude (km)" value={c.altitude_km} min={300} max={2000} step={10}
                  onChange={(v) => setC("altitude_km", v)} />
        <NumField label="Inclination (°)" value={c.inclination_deg} min={0} max={100} step={1}
                  onChange={(v) => setC("inclination_deg", v)} />
        <NumField label="Planes" value={c.planes} min={3} max={72}
                  onChange={(v) => setC("planes", v)} />
        <NumField label="Satellites per plane" value={c.sats_per_plane} min={3} max={72}
                  onChange={(v) => setC("sats_per_plane", v)} />
        <NumField label="Phasing (F)" value={c.phasing} min={0} max={Math.max(0, c.planes - 1)}
                  onChange={(v) => setC("phasing", v)} />
        <div className="dim" style={{ alignSelf: "end", paddingBottom: 6 }}>
          {c.planes * c.sats_per_plane} satellites
        </div>
      </div>

      <div className="summary-box">
        {preview.error && <div className="warn">{preview.error}</div>}
        {s && (
          <>
            <div className="summary-grid">
              <span>Orbital period</span><b>{s.period_min} min</b>
              <span>Orbital speed</span><b>{s.orbital_speed_kms} km/s</b>
              <span>Neighbor spacing</span><b>{s.intra_plane_spacing_km} km</b>
              <span>Footprint radius</span><b>{s.footprint_radius_km} km</b>
              <span>Mean in view (est.)</span><b>{s.mean_sats_in_view_estimate}</b>
              <span>Stations / flows</span><b>{s.n_stations} / {s.n_flows}</b>
            </div>
            {!s.intra_plane_links_in_range && (
              <div className="warn">
                Neighbors in a plane are {s.intra_plane_spacing_km} km apart, beyond the {s.max_isl_range_km} km
                ISL range, so intra-plane links will be down. Raise the max ISL range or add satellites per plane.
              </div>
            )}
          </>
        )}
      </div>

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