import { useState } from "react";
import type { AgentState, Doc, Topic } from "../types";
import { ago, label } from "../format";
import MemoryGraph, { TYPE_COLORS } from "./MemoryGraph";

const VIEWS = ["Graph", "Topics", "Documents", "Facts", "Permissions"] as const;
type View = (typeof VIEWS)[number];

export default function MemoryPanel({ state }: { state: AgentState }) {
  const [view, setView] = useState<View>("Graph");
  const m = state.memory;
  return (
    <div>
      <div className="subtabs">
        {VIEWS.map((v) => (
          <button key={v} className={v === view ? "active" : ""} onClick={() => setView(v)}>
            {v}
          </button>
        ))}
      </div>
      {view === "Graph" && <MemoryGraph state={state} />}
      {view === "Topics" && <TopicIndex topics={m.topics} />}
      {view === "Documents" && <Documents docs={m.documents} />}
      {view === "Facts" && (
        <div>
          {m.nodes.length === 0 && <div className="empty">No facts yet.</div>}
          {m.nodes.map((n) => (
            <div className="card" key={n.id}>
              <div className="row">
                <i className="dot" style={{ background: TYPE_COLORS[n.type] }} />
                <strong className="grow">{n.title}</strong>
                <span className="badge">{label(n.type)}</span>
                <span className="faint small">{ago(n.updated_at)}</span>
              </div>
              {n.body && <div className="muted" style={{ marginTop: 4 }}>{n.body}</div>}
              <div className="faint small" style={{ marginTop: 4 }}>
                <code>{n.id}</code>
                {n.topic_id && <> · topic <code>{n.topic_id}</code></>}
                {" · "}
                {n.source_event_ids.length} source event{n.source_event_ids.length === 1 ? "" : "s"}
              </div>
            </div>
          ))}
          {m.edges.length > 0 && (
            <div className="section" style={{ marginTop: 16 }}>
              <h3>Relationships</h3>
              {m.edges.map((e) => (
                <div key={`${e.source_id}-${e.type}-${e.target_id}`} className="small">
                  <code>{e.source_id}</code> <span className="badge">{label(e.type)}</span> <code>{e.target_id}</code>
                  {e.note && <span className="muted"> · {e.note}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {view === "Permissions" && (
        <div>
          {m.permissions.length === 0 && <div className="empty">No permissions remembered.</div>}
          {m.permissions.map((p, i) => (
            <div className="card row" key={i}>
              <code className="grow">{p.tool}.{p.function}</code>
              <span className={`badge ${p.granted ? "good" : "bad"}`}>{p.granted ? "granted" : "declined"}</span>
              <span className="badge">{p.scope}</span>
              <span className="faint small">{p.detail}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TopicIndex({ topics }: { topics: Topic[] }) {
  const [showArchived, setShowArchived] = useState(false);
  const visible = topics.filter((t) => showArchived || !t.archived);
  const ids = new Set(visible.map((t) => t.id));
  const roots = visible.filter((t) => !t.parent_id || !ids.has(t.parent_id));
  const children = (id: string) => visible.filter((t) => t.parent_id === id);

  function render(t: Topic, depth: number) {
    return (
      <div key={t.id} style={{ marginLeft: depth * 18 }}>
        <div className="card">
          <div className="row">
            <strong>{t.title}</strong>
            {t.category && <span className="badge">{t.category}</span>}
            {t.new_info && <span className="badge accent">new: {t.new_info}</span>}
            {t.archived && <span className="badge">archived</span>}
            <span className="grow" />
            {t.due && <span className="badge warn">due {t.due}</span>}
            {t.importance && <span className="badge">{t.importance}</span>}
          </div>
          {t.summary && <div className="muted" style={{ marginTop: 4 }}>{t.summary}</div>}
          {t.progress > 0 && (
            <div className="row" style={{ marginTop: 6 }}>
              <div className="progress grow"><div style={{ width: `${Math.round(t.progress * 100)}%` }} /></div>
              <span className="small faint">{Math.round(t.progress * 100)}% {t.progress_note}</span>
            </div>
          )}
          {t.triggers.length > 0 && (
            <div className="row small" style={{ marginTop: 6 }}>
              {t.triggers.map((tr, i) => (
                <span key={i} className={`badge ${tr.user_override ? "accent" : ""}`} title={tr.reasoning}>
                  {tr.type}: {tr.condition}
                  {tr.user_override ? " (user)" : ""}
                </span>
              ))}
            </div>
          )}
          <div className="faint small" style={{ marginTop: 4 }}>
            <code>{t.id}</code> · updated {ago(t.updated_at)}
            {t.last_seen_at && <> · seen {ago(t.last_seen_at)}</>}
          </div>
        </div>
        {children(t.id).map((c) => render(c, depth + 1))}
      </div>
    );
  }

  return (
    <div>
      <label className="row small muted" style={{ marginBottom: 10 }}>
        <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} /> show archived
      </label>
      {roots.length === 0 && <div className="empty">No topics yet.</div>}
      {roots.map((t) => render(t, 0))}
    </div>
  );
}

function Documents({ docs }: { docs: Doc[] }) {
  if (!docs.length) return <div className="empty">No documents yet.</div>;
  return (
    <div>
      {docs.map((d) => (
        <details className="card" key={d.id}>
          <summary className="row">
            <strong className="grow">{d.title}</strong>
            <span className={`badge ${d.status === "complete" ? "good" : d.status === "waiting" ? "warn" : ""}`}>{d.status}</span>
            <span className="faint small">{d.sections.length} sections · {ago(d.updated_at)}</span>
          </summary>
          <pre className="json">{JSON.stringify(d, null, 2)}</pre>
        </details>
      ))}
    </div>
  );
}
