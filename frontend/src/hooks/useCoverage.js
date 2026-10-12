import { useCallback, useRef, useState } from "react";
import { API_URL } from "../config";
import { readError } from "../utils";

export function useCoverage() {
  const [state, setState] = useState({ loading: false, data: null, error: null });
  const latest = useRef(0);

  // Pass either { scenarioId } (saved or default) or { config } (an unsaved draft).
  const compute = useCallback(async ({ scenarioId = null, config = null, params }) => {
    const id = ++latest.current;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      let r;
      if (config) {
        r = await fetch(`${API_URL}/coverage/preview`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ config, ...params }),
        });
      } else {
        const query = new URLSearchParams(params);
        if (scenarioId != null) query.set("scenario_id", scenarioId);
        r = await fetch(`${API_URL}/coverage?${query}`);
      }
      if (!r.ok) throw new Error(await readError(r));
      const data = await r.json();
      if (id === latest.current) setState({ loading: false, data, error: null });
    } catch (e) {
      if (id === latest.current) setState({ loading: false, data: null, error: e.message });
    }
  }, []);

  const clear = useCallback(() => {
    latest.current += 1;
    setState({ loading: false, data: null, error: null });
  }, []);

  return { ...state, compute, clear };
}