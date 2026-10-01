import { fmtTime, stationName } from "../utils";

const label = (e) => {
  if (e.reason === "outage") return `OUTAGE (lost S${e.from_sat})`;
  if (e.reason === "lost") return `handoff S${e.from_sat} → S${e.to_sat} (lost view)`;
  return `handoff S${e.from_sat} → S${e.to_sat} (better sat)`;
};

export default function EventLog({ init, events }) {
  return (
    <div className="panel">
      <h3>Handoffs and outages</h3>
      <div className="events">
        {events.length === 0 && <div className="dim">No events yet.</div>}
        {events.map((e) => (
          <div key={e.key} className={e.reason === "outage" ? "ev bad" : "ev"}>
            <span className="dim">{fmtTime(e.t)}</span> {stationName(init, `G${e.station}`)}: {label(e)}
          </div>
        ))}
      </div>
    </div>
  );
}