export default function ScenarioPicker({ list, value, onChange }) {
  return (
    <label className="picker">
      Scenario
      <select value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}>
        <option value="">Default (Starlink-like shell)</option>
        {list.map((s) => (
          <option key={s.id} value={s.id}>{s.name} · {s.n_sats} sats</option>
        ))}
      </select>
    </label>
  );
}