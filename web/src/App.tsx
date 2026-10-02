import { useCallback, useEffect, useMemo, useState } from "react";
import { makeApi } from "./api";
import { useAgentState } from "./useAgentState";
import { load, save } from "./storage";
import TopBar from "./components/TopBar";
import Experience from "./experience/Experience";
import MemoryPanel from "./panels/MemoryPanel";
import ToolsPanel from "./panels/ToolsPanel";
import DataPanel from "./panels/DataPanel";
import TracesPanel from "./panels/TracesPanel";

const TABS = ["Memory", "Tools", "Data", "Traces"] as const;
type Tab = (typeof TABS)[number];

export default function App() {
  const [user, setUser] = useState(() => load("user", "demo"));
  const [theme, setTheme] = useState(() => load("theme", ""));
  const [tab, setTab] = useState<Tab>(() => (load("tab", "Memory") as Tab));
  const [toast, setToast] = useState<string | null>(null);
  const api = useMemo(() => makeApi(user), [user]);
  const { state, connected, error } = useAgentState(api);

  useEffect(() => {
    if (theme) document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;
    save("theme", theme);
  }, [theme]);
  useEffect(() => save("user", user), [user]);
  useEffect(() => save("tab", tab), [tab]);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 5000);
    return () => clearTimeout(t);
  }, [toast]);

  /** Run an action, surfacing failures as a toast. */
  const act = useCallback(async (fn: () => Promise<unknown>) => {
    try {
      await fn();
    } catch (e) {
      setToast(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const counts: Record<Tab, number> = {
    Memory: state ? state.memory.nodes.length + state.memory.topics.filter((t) => !t.archived).length : 0,
    Tools: state?.memory.tools.length ?? 0,
    Data: state?.ambient.sources.length ?? 0,
    Traces: state?.memory.sessions.length ?? 0,
  };

  return (
    <div className="app">
      <TopBar
        api={api}
        state={state}
        user={user}
        onUser={setUser}
        theme={theme}
        onTheme={setTheme}
        connected={connected}
        act={act}
      />
      <div className="workspace">
        <div className="experience-pane">
          {state ? (
            <Experience state={state} api={api} act={act} />
          ) : (
            <div className="empty">{error ? `Cannot reach the agent: ${error}` : "Loading…"}</div>
          )}
        </div>
        <div className="panels">
          <div className="tabs" role="tablist">
            {TABS.map((t) => (
              <button key={t} role="tab" className={`tab ${t === tab ? "active" : ""}`} onClick={() => setTab(t)}>
                {t}
                <span className="count">{counts[t] || ""}</span>
              </button>
            ))}
          </div>
          <div className="panel">
            {state &&
              (tab === "Memory" ? (
                <MemoryPanel state={state} />
              ) : tab === "Tools" ? (
                <ToolsPanel state={state} api={api} act={act} />
              ) : tab === "Data" ? (
                <DataPanel state={state} api={api} act={act} />
              ) : (
                <TracesPanel state={state} />
              ))}
          </div>
        </div>
      </div>
      {toast && <div className="toast" onClick={() => setToast(null)}>{toast}</div>}
    </div>
  );
}
