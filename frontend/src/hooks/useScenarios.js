import { useCallback, useEffect, useMemo, useState } from "react";
import { API_URL } from "../config";
import { readError } from "../utils";

export function useScenarios() {
  const [list, setList] = useState([]);
  const [defaultScenario, setDefaultScenario] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch(`${API_URL}/scenarios`);
      if (r.ok) setList(await r.json());
    } catch {
      /* backend not reachable yet */
    }
  }, []);

  useEffect(() => {
    refresh();
    fetch(`${API_URL}/scenarios/default`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setDefaultScenario(d))
      .catch(() => {});
  }, [refresh]);

  const load = useCallback(async (id) => {
    const r = await fetch(`${API_URL}/scenarios/${id}`);
    return r.ok ? r.json() : null;
  }, []);

  const save = useCallback(async (id, body) => {
    const r = await fetch(id ? `${API_URL}/scenarios/${id}` : `${API_URL}/scenarios`, {
      method: id ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(await readError(r));
    const data = await r.json();
    await refresh();
    return data;
  }, [refresh]);

  const remove = useCallback(async (id) => {
    await fetch(`${API_URL}/scenarios/${id}`, { method: "DELETE" });
    await refresh();
  }, [refresh]);

  return useMemo(
    () => ({ list, defaultScenario, refresh, load, save, remove }),
    [list, defaultScenario, refresh, load, save, remove]
  );
}