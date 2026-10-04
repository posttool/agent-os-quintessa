import { Fragment, useState } from "react";
import type { Api } from "../api";
import type { AgentState, AppSearchResult, Tool } from "../types";
import AppIcon from "../components/AppIcon";
import { label } from "../format";

const TEMPLATE = {
  name: "restaurant_reservations",
  description: "Find restaurants and book or cancel tables.",
  kind: "llm",
  grounding: "You are a restaurant booking service. Report realistic availability and confirmations.",
  functions: [
    { name: "search", description: "Find tables", oversight: "auto_from_memory",
      parameters: [{ name: "query", type: "string" }, { name: "party_size", type: "integer" }] },
    { name: "book", description: "Book a table", oversight: "confirm_once", long_running: true,
      parameters: [{ name: "restaurant", type: "string" }, { name: "time", type: "string" }] },
  ],
};

const OVERSIGHT_TONE: Record<string, string> = { auto: "good", auto_from_memory: "good", confirm_once: "warn", always_ask: "bad" };

export default function ToolsPanel({ state, api, act }: { state: AgentState; api: Api; act: (fn: () => Promise<unknown>) => Promise<void> }) {
  const [draft, setDraft] = useState<string | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const tools = [...state.memory.tools]
    .filter((t) => t.kind !== "app")
    .sort((a, b) => Number(b.kind === "builtin") - Number(a.kind === "builtin"));

  function save() {
    let tool: unknown;
    try {
      tool = JSON.parse(draft ?? "");
    } catch (e) {
      setParseError(String(e));
      return;
    }
    setParseError(null);
    void act(async () => {
      await api.putTool(tool);
      setDraft(null);
    });
  }

  return (
    <div>
      <Apps state={state} api={api} act={act} />
      <h3 style={{ margin: "18px 0 8px" }}>Other tools</h3>
      <div className="row" style={{ marginBottom: 12 }}>
        <span className="muted grow">
          Built-in tools are web access and device control. Everything else is created on demand by the agent or by you.
        </span>
        <button className="primary" onClick={() => setDraft(JSON.stringify(TEMPLATE, null, 2))}>New tool</button>
      </div>
      {draft !== null && (
        <div className="card">
          <div className="field">
            <span>Tool definition (JSON). Kinds: llm, web_api, mcp, code. Oversight: auto, auto_from_memory, confirm_once, always_ask.</span>
            <textarea rows={16} value={draft} onChange={(e) => setDraft(e.target.value)} />
          </div>
          {parseError && <p className="small" style={{ color: "var(--bad)" }}>{parseError}</p>}
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <button onClick={() => setDraft(null)}>Cancel</button>
            <button className="primary" onClick={save}>Save tool</button>
          </div>
        </div>
      )}
      {tools.map((t) => (
        <div className="card" key={t.name}>
          <div className="row">
            <strong>{t.name}</strong>
            <span className={`badge ${t.kind === "builtin" ? "accent" : ""}`}>{t.kind}</span>
            <span className="faint small">by {t.created_by}</span>
            <span className="grow" />
            {t.kind !== "builtin" && (
              <>
                <button onClick={() => setDraft(JSON.stringify(t, null, 2))}>Edit</button>
                <button className="danger" onClick={() => confirm(`Delete ${t.name}?`) && act(() => api.deleteTool(t.name))}>Delete</button>
              </>
            )}
          </div>
          <div className="muted" style={{ margin: "4px 0 6px" }}>{t.description}</div>
          <Functions tool={t} />
          {t.grounding && (
            <details className="small" style={{ marginTop: 6 }}>
              <summary className="muted">grounding</summary>
              <pre className="json">{t.grounding}</pre>
            </details>
          )}
        </div>
      ))}
    </div>
  );
}

function Functions({ tool }: { tool: Tool }) {
  return (
    <div className="fn-list">
      {tool.functions.map((f) => (
        <div key={f.name} className="fn-row small">
          <code className="fn-sig">
            {signature(f).map((part, i) => (
              <Fragment key={i}>
                {i > 0 && " "}
                <span className="fn-param">{part}</span>
              </Fragment>
            ))}
          </code>
          <span className="faint fn-desc">{f.description}</span>
          <span className="fn-badges">
            {f.long_running && <span className="badge">long-running</span>}
            <span className={`badge ${OVERSIGHT_TONE[f.oversight]}`}>{label(f.oversight)}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

/** Signature pieces that break between parameters, and inside one only when it can't fit a line. */
function signature(f: Tool["functions"][number]): string[] {
  const params = f.parameters.map((p) => `${p.name}${p.required ? "" : "?"}: ${p.type}`);
  if (params.length === 0) return [`${f.name}() → ${f.returns}`];
  params[0] = `${f.name}(${params[0]}`;
  params[params.length - 1] += `) → ${f.returns}`;
  return params.map((p, i) => (i < params.length - 1 ? `${p},` : p));
}

function Apps({ state, api, act }: { state: AgentState; api: Api; act: (fn: () => Promise<unknown>) => Promise<void> }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<AppSearchResult[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const apps = state.memory.tools.filter((t) => t.kind === "app");

  function search() {
    if (!query.trim()) return;
    setBusy("search");
    void act(async () => setResults(await api.searchApps(query.trim()))).finally(() => setBusy(null));
  }

  function install(r: AppSearchResult) {
    setBusy(r.app_id);
    void act(async () => {
      await api.installApp(r);
      setResults(await api.searchApps(query.trim()));
    }).finally(() => setBusy(null));
  }

  return (
    <div>
      <div className="row" style={{ marginBottom: 8 }}>
        <h3 className="grow" style={{ margin: 0 }}>Apps</h3>
      </div>
      <div className="muted small" style={{ marginBottom: 8 }}>
        The agent installs apps from the store ({state.apps.store}) whenever it needs one, without asking. Installed apps are simulated by a model for now.
      </div>
      <div className="row" style={{ marginBottom: 10 }}>
        <input className="grow" placeholder="Search the app store" value={query}
          onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} />
        <button onClick={search} disabled={busy === "search"}>{busy === "search" ? "Searching…" : "Search"}</button>
      </div>
      {results && (
        <div className="card">
          {results.length === 0 && <div className="muted">No apps found.</div>}
          {results.map((r) => (
            <div key={r.app_id} className="row" style={{ padding: "4px 0" }}>
              <AppIcon listing={r} name={r.title} size={32} />
              <div className="grow">
                <div><strong>{r.title}</strong> <span className="faint small">{r.developer}</span></div>
                <div className="muted small">{r.summary}</div>
              </div>
              {r.installed_as
                ? <span className="badge good">installed</span>
                : <button onClick={() => install(r)} disabled={busy !== null}>{busy === r.app_id ? "Installing…" : "Install"}</button>}
            </div>
          ))}
        </div>
      )}
      {apps.length === 0 && <div className="muted small">No apps installed yet.</div>}
      {apps.map((t) => (
        <div className="card" key={t.name}>
          <div className="row">
            <AppIcon listing={t.listing} name={t.name} size={36} />
            <div className="grow">
              <div className="row" style={{ gap: 6 }}>
                <strong>{t.listing?.title ?? t.name}</strong>
                <code className="faint small">{t.name}</code>
                <span className="badge">{t.binding}</span>
                <span className="badge">sign-in: {t.auth.kind === "none" ? "none" : `${t.auth.kind}, ${t.auth.state}`}</span>
                <span className="faint small">by {t.created_by}</span>
              </div>
              <div className="faint small">
                {t.listing?.developer}
                {t.listing?.store_url && <> · <a href={t.listing.store_url} target="_blank" rel="noreferrer">store page</a></>}
              </div>
            </div>
            {t.listing && (
              <button className="danger" onClick={() => confirm(`Uninstall ${t.listing!.title}?`) && act(() => api.uninstallApp(t.listing!.app_id))}>
                Uninstall
              </button>
            )}
          </div>
          <div className="muted" style={{ margin: "4px 0 6px" }}>{t.description}</div>
          <Functions tool={t} />
        </div>
      ))}
    </div>
  );
}
