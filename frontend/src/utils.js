export const fmtTime = (t) => {
  const s = Math.round(t);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `T+${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
};

export const pct = (x, d = 1) => (x == null ? "–" : `${(x * 100).toFixed(d)}%`);
export const num = (x, d = 1) => (x == null ? "–" : x.toFixed(d));

// 0 -> green, ~0.5 -> yellow, >= 1 -> red
export function utilColor(u) {
  const c = Math.max(0, Math.min(1, u ?? 0));
  return `hsl(${120 - 120 * c}, 85%, 55%)`;
}

export const stationName = (init, id) => init?.stations?.[Number(id.slice(1))]?.name ?? id;

export async function readError(r) {
  try {
    const body = await r.json();
    if (Array.isArray(body.detail)) {
      return body.detail.map((d) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join("; ");
    }
    return typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
  } catch {
    return `HTTP ${r.status}`;
  }
}