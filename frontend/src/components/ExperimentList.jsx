export default function ExperimentList({ list, selectedId, onSelect, onDelete }) {
  return (
    <div className="panel">
      <h3>Experiments</h3>
      {list.length === 0 && <div className="dim">None yet.</div>}
      <div className="exp-list">
        {list.map((e) => (
          <div key={e.id} className={`exp-item ${e.id === selectedId ? "sel" : ""}`} onClick={() => onSelect(e.id)}>
            <div>
              <strong>{e.name}</strong> <span className={`chip ${e.status}`}>{e.status}</span>
            </div>
            <div className="dim">{e.preset} · {e.arms.length} arms</div>
            <button className="link" onClick={(ev) => {
              ev.stopPropagation();
              if (window.confirm("Delete this experiment and its runs?")) onDelete(e.id);
            }}>delete</button>
          </div>
        ))}
      </div>
    </div>
  );
}