import { useEffect, useRef, useState } from "react";
import type { Api } from "./api";
import type { AgentState } from "./types";

/** Live state for one user: refetches whenever the server says it changed. */
export function useAgentState(api: Api) {
  const [state, setState] = useState<AgentState | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inflight = useRef(false);
  const again = useRef(false);

  useEffect(() => {
    let alive = true;
    setState(null);

    async function refresh() {
      if (inflight.current) {
        again.current = true;
        return;
      }
      inflight.current = true;
      try {
        const next = await api.state();
        if (alive) {
          setState(next);
          setError(null);
        }
      } catch (e) {
        if (alive) setError(String(e));
      } finally {
        inflight.current = false;
        if (again.current && alive) {
          again.current = false;
          void refresh();
        }
      }
    }

    const source = new EventSource(api.streamUrl);
    source.addEventListener("change", () => void refresh());
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    void refresh();
    return () => {
      alive = false;
      source.close();
    };
  }, [api]);

  return { state, connected, error };
}
