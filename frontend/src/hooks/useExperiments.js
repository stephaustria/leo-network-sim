import { useCallback, useEffect, useState } from "react";
import { API_URL } from "../config";

async function readError(r) {
  try {
    const body = await r.json();
    if (Array.isArray(body.detail)) return body.detail.map((d) => d.msg ?? JSON.stringify(d)).join("; ");
    return typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
  } catch {
    return `HTTP ${r.status}`;
  }
}

export function useExperiments() {
  const [list, setList] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [timelines, setTimelines] = useState(null);

  const refreshList = useCallback(async () => {
    try {
      const r = await fetch(`${API_URL}/experiments?limit=30`);
      if (r.ok) setList(await r.json());
    } catch {
      /* backend not reachable yet */
    }
  }, []);

  const loadSelected = useCallback(async (id) => {
    if (!id) {
      setDetail(null);
      setTimelines(null);
      return;
    }
    try {
      const [d, t] = await Promise.all([
        fetch(`${API_URL}/experiments/${id}`),
        fetch(`${API_URL}/experiments/${id}/timelines`),
      ]);
      if (d.ok) setDetail(await d.json());
      if (t.ok) setTimelines(await t.json());
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => { refreshList(); }, [refreshList]);
  useEffect(() => { loadSelected(selectedId); }, [selectedId, loadSelected]);

  const running = list.some((e) => e.status === "running") || detail?.status === "running";
  useEffect(() => {
    if (!running) return undefined;
    const id = setInterval(() => { refreshList(); loadSelected(selectedId); }, 3000);
    return () => clearInterval(id);
  }, [running, selectedId, refreshList, loadSelected]);

  const create = useCallback(async (body) => {
    const r = await fetch(`${API_URL}/experiments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(await readError(r));
    const data = await r.json();
    await refreshList();
    setSelectedId(data.experiment_id);
    return data.experiment_id;
  }, [refreshList]);

  const remove = useCallback(async (id) => {
    await fetch(`${API_URL}/experiments/${id}`, { method: "DELETE" });
    if (id === selectedId) setSelectedId(null);
    await refreshList();
  }, [refreshList, selectedId]);

  return { list, selectedId, select: setSelectedId, detail, timelines, create, remove };
}