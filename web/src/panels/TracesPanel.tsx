import { useState } from "react";
import type { AgentState, Session } from "../types";
import { label, time } from "../format";

const STATUS_TONE: Record<string, string> = {
  running: "accent", waiting_for_user: "warn", complete: "good", failed: "bad", stopped: "",
};

export default function TracesPanel({ state }: { state: AgentState }) {
  const [filter, setFilter] = useState("");
  const sessions = [...state.memory.sessions]
    .sort((a, b) => b.started_at.localeCompare(a.started_at))
    .filter((s) => !filter || s.trigger.kind === filter);
  const kinds = [...new Set(state.memory.sessions.map((s) => s.trigger.kind))];

  return (
    <div>
      <div className="subtabs">
        <button className={!filter ? "active" : ""} onClick={() => setFilter("")}>All triggers</button>
        {kinds.map((k) => (
          <button key={k} className={filter === k ? "active" : ""} onClick={() => setFilter(k)}>{label(k)}</button>
        ))}
      </div>
      {sessions.length === 0 && <div className="empty">No reasoning yet.</div>}
      {sessions.map((s) => <SessionTrace key={s.id} session={s} />)}
    </div>
  );
}

function SessionTrace({ session }: { session: Session }) {
  const t = session.trigger;
  const duration = session.ended_at ? ((new Date(session.ended_at).getTime() - new Date(session.started_at).getTime()) / 1000).toFixed(1) : null;
  return (
    <details className="card" open={session.status === "running" || session.status === "waiting_for_user"}>
      <summary>
        <div className="row">
          <span className="faint mono small">{time(session.started_at)}</span>
          <span className="badge">{label(t.kind)}</span>
          <span className="grow" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {t.sender && <strong>{t.sender}: </strong>}
            {t.content}
          </span>
          <span className="faint small">{session.steps.length} steps{duration && ` · ${duration}s`}</span>
          <span className={`badge ${STATUS_TONE[session.status]}`}>{label(session.status)}</span>
        </div>
      </summary>
      <div style={{ marginTop: 10 }}>
        <div className="faint small" style={{ marginBottom: 8 }}>
          trigger <code>{t.id}</code> from {t.source}{t.device && ` on ${t.device}`} · session <code>{session.id}</code>
        </div>
        {session.steps.map((step) => (
          <div key={step.index} className={`step ${step.error ? "err" : ""}`}>
            <div className="row">
              <strong>{step.index + 1}. {step.capability ? label(step.capability) : "—"}</strong>
              {step.model && <span className="badge">{step.model}</span>}
              <span className="faint small">{time(step.started_at)}</span>
            </div>
            {step.focus && <div><span className="muted">focus:</span> {step.focus}</div>}
            {step.rationale && <div className="muted small">why: {step.rationale}</div>}
            {step.summary && <div style={{ marginTop: 2 }}>→ {step.summary}</div>}
            {step.error && <div style={{ color: "var(--bad)" }}>{step.error}</div>}
            {Object.keys(step.output).length > 0 && (
              <details className="small">
                <summary className="muted">output</summary>
                <pre className="json">{JSON.stringify(step.output, null, 2)}</pre>
              </details>
            )}
          </div>
        ))}
        {session.permissions.length > 0 && (
          <div className="row small" style={{ marginTop: 6 }}>
            {session.permissions.map((p, i) => (
              <span key={i} className={`badge ${p.granted ? "good" : "bad"}`}>
                {p.tool}.{p.function} {p.granted ? "granted" : "declined"}
              </span>
            ))}
          </div>
        )}
      </div>
    </details>
  );
}
