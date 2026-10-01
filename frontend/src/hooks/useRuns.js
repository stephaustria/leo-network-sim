import { useCallback, useEffect, useState } from "react";
import { API_URL } from "../config";

export function useRuns() {
  const [runs, setRuns] = useState([]);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch(`${API_URL}/runs?limit=30`);
      if (r.ok) setRuns(await r.json());
    } catch {
      /* backend not reachable yet */
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!runs.some((r) => r.status === "running")) return undefined;
    const id = setInterval(refresh, 2000);
    return () => clearInterval(id);
  }, [runs, refresh]);

  const create = useCallback(
    async (params) => {
      const r = await fetch(`${API_URL}/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      await refresh();
      return data.id;
    },
    [refresh]
  );

  return { runs, refresh, create };
}