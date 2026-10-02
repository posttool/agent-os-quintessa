import { useState } from "react";
import type { Api } from "../api";
import type { AgentState } from "../types";
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
  const tools = [...state.memory.tools].sort((a, b) => Number(b.kind === "builtin") - Number(a.kind === "builtin"));

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
          {t.functions.map((f) => (
            <div key={f.name} className="row small" style={{ padding: "3px 0", borderTop: "1px solid var(--border)" }}>
              <code>
                {f.name}({f.parameters.map((p) => `${p.name}${p.required ? "" : "?"}: ${p.type}`).join(", ")}) → {f.returns}
              </code>
              <span className="grow faint">{f.description}</span>
              {f.long_running && <span className="badge">long-running</span>}
              <span className={`badge ${OVERSIGHT_TONE[f.oversight]}`}>{label(f.oversight)}</span>
            </div>
          ))}
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
