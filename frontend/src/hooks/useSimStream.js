import { useCallback, useEffect, useRef, useState } from "react";
import { WS_URL } from "../config";

const HISTORY_LIMIT = 400;

export function useSimStream() {
  const wsRef = useRef(null);
  const [status, setStatus] = useState("closed"); // closed | connecting | open
  const [init, setInit] = useState(null);
  const [frame, setFrame] = useState(null);
  const [serverState, setServerState] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState(null);
  const [finished, setFinished] = useState(false);

  const close = useCallback(() => {
    const ws = wsRef.current;
    if (ws) {
      ws.onopen = ws.onclose = ws.onmessage = ws.onerror = null;
      ws.close();
    }
    wsRef.current = null;
    setStatus("closed");
  }, []);

  const open = useCallback(
    (path) => {
      close();
      setInit(null);
      setFrame(null);
      setServerState(null);
      setHistory([]);
      setError(null);
      setFinished(false);
      setStatus("connecting");

      const ws = new WebSocket(`${WS_URL}${path}`);
      wsRef.current = ws;
      ws.onopen = () => setStatus("open");
      ws.onclose = () => {
        if (wsRef.current === ws) {
          wsRef.current = null;
          setStatus("closed");
        }
      };
      ws.onerror = () => setError("WebSocket error. Is the backend running?");
      ws.onmessage = (e) => {
        const m = JSON.parse(e.data);
        switch (m.type) {
          case "init":
            setInit(m);
            break;
          case "state":
            setServerState(m);
            break;
          case "frame":
            setFrame(m);
            setFinished(false);
            setHistory((h) => {
              const last = h[h.length - 1];
              const base = last && last.t >= m.t ? [] : h; // restarted: start a new series
              const next = [...base, m.metrics];
              return next.length > HISTORY_LIMIT ? next.slice(-HISTORY_LIMIT) : next;
            });
            break;
          case "done":
            setFinished(true);
            break;
          case "error":
            setError(m.message);
            break;
          default:
            break;
        }
      };
    },
    [close]
  );

  const send = useCallback((cmd) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(cmd));
  }, []);

  useEffect(() => close, [close]);

  return { status, init, frame, serverState, history, error, finished, open, close, send };
}