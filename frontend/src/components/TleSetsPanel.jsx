import { useState } from "react";

const GROUPS = ["stations", "iridium-NEXT", "starlink", "oneweb", "gps-ops", "weather", "geo"];

export default function TleSetsPanel({ tle, onAddToScenario }) {
  const [group, setGroup] = useState("iridium-NEXT");
  const [fetching, setFetching] = useState(false);
  const [message, setMessage] = useState(null);
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState(null);

  const fetchGroup = async () => {
    setFetching(true);
    setError(null);
    setMessage(null);
    try {
      const r = await tle.fetchGroup(group.trim());
      setMessage(r.reused
        ? `Reused the stored fetch "${r.name}" (${r.n_sats} satellites).`
        : `Stored ${r.n_sats} satellites from CelesTrak.`);
    } catch (e) {
      setError(e.message);
    } finally {
      setFetching(false);
    }
  };

  const addPasted = async () => {
    setAdding(true);
    setError(null);
    setMessage(null);
    try {
      const r = await tle.create(name.trim(), text);
      setMessage(`Stored ${r.n_sats} satellites.`);
      setName("");
      setText("");
    } catch (e) {
      setError(e.message);
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="panel">
      <h3>Real satellites (TLE sets)</h3>

      <label>
        CelesTrak group
        <div className="row" style={{ marginBottom: 0 }}>
          <input type="text" list="celestrak-groups" value={group} onChange={(e) => setGroup(e.target.value)} />
          <datalist id="celestrak-groups">
            {GROUPS.map((g) => <option key={g} value={g} />)}
          </datalist>
          <button disabled={fetching || !group.trim()} onClick={fetchGroup}>
            {fetching ? "Fetching…" : "Fetch"}
          </button>
        </div>
      </label>
      <div className="hint">A fetch of the same group newer than 2 hours is reused. Big groups can take a while.</div>

      <label>
        Or paste TLE text
        <input type="text" value={name} placeholder="Name for this set" maxLength={80}
               onChange={(e) => setName(e.target.value)} />
        <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)}
                  placeholder={"ISS (ZARYA)\n1 25544U 98067A   19343.69339541 ...\n2 25544  51.6439 211.2001 ..."} />
      </label>
      <div style={{ marginTop: 8 }}>
        <button disabled={adding || !name.trim() || !text.trim()} onClick={addPasted}>
          {adding ? "Adding…" : "Add pasted TLEs"}
        </button>
      </div>

      {message && <div className="hint">{message}</div>}
      {error && <div className="warn">{error}</div>}

      <div className="tle-list">
        {tle.list.length === 0 && <div className="dim">No TLE sets yet.</div>}
        {tle.list.map((s) => (
          <div className="tle-row" key={s.id}>
            <div>
              <b>{s.name}</b>
              <div className="dim">
                {s.n_sats} sats · epoch {String(s.epoch).slice(0, 16).replace("T", " ")} · {s.source}
              </div>
            </div>
            <button onClick={() => onAddToScenario(s.id)}>Add to scenario</button>
          </div>
        ))}
      </div>
    </div>
  );
}