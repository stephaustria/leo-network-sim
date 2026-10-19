import { useCallback, useEffect, useMemo, useState } from "react";
import { API_URL } from "../config";
import { readError } from "../utils";

export function useTleSets() {
  const [list, setList] = useState([]);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch(`${API_URL}/tle-sets`);
      if (r.ok) setList(await r.json());
    } catch {
      /* backend not reachable yet */
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const post = useCallback(async (path, body) => {
    const r = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(await readError(r));
    const data = await r.json();
    await refresh();
    return data;
  }, [refresh]);

  const create = useCallback((name, text) => post("/tle-sets", { name, text }), [post]);
  const fetchGroup = useCallback((group) => post("/tle-sets/fetch", { group }), [post]);

  return useMemo(() => ({ list, refresh, create, fetchGroup }), [list, refresh, create, fetchGroup]);
}