import { useState } from "react";
import type { AgentState, AppSearchResult, Session, ShadowDecision } from "../types";
import AppIcon from "../components/AppIcon";
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
  const shadow = new Map((session.shadow_decisions ?? []).map((d) => [d.step_index, d]));
  const finish = (session.shadow_decisions ?? []).find((d) => (d.drove ? d.choice : d.llm_choice) === "done");
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
          {session.ambient_filter && !session.ambient_filter.error && (
            <span className="badge" title={`${session.ambient_filter.model || "Jev"}: P(this matters), threshold ${session.ambient_filter.threshold}`}>
              Jev p {session.ambient_filter.matters.toFixed(2)}
            </span>
          )}
          {session.ambient_filter?.skipped
            ? <span className="badge">skipped</span>
            : <span className={`badge ${STATUS_TONE[session.status]}`}>{label(session.status)}</span>}
        </div>
      </summary>
      <div style={{ marginTop: 10 }}>
        <div className="faint small" style={{ marginBottom: 8 }}>
          trigger <code>{t.id}</code> from {t.source}{t.device && ` on ${t.device}`} · session <code>{session.id}</code>
        </div>
        {session.ambient_filter && <AmbientFilterDetail decision={session.ambient_filter} />}
        {session.steps.map((step) => (
          <div key={step.index} className={`step ${step.error ? "err" : ""}`}>
            <div className="row">
              <strong>{step.index + 1}. {step.capability ? label(step.capability) : "—"}</strong>
              {step.model && <span className="badge">{step.model}</span>}
              <JevBadge decision={shadow.get(step.index)} />
              <span className="faint small">{time(step.started_at)}</span>
            </div>
            {step.focus && <div><span className="muted">focus:</span> {step.focus}</div>}
            {step.rationale && <div className="muted small">why: {step.rationale}</div>}
            <Shadow decision={shadow.get(step.index)} />
            {step.summary && <div style={{ marginTop: 2 }}>→ {step.summary}</div>}
            {step.error && <div style={{ color: "var(--bad)" }}>{step.error}</div>}
            {Array.isArray(step.output.candidates) && step.output.candidates.length > 0 && (
              <Candidates output={step.output} />
            )}
            {Object.keys(step.output).length > 0 && (
              <details className="small">
                <summary className="muted">output</summary>
                <pre className="json">{JSON.stringify(step.output, null, 2)}</pre>
              </details>
            )}
          </div>
        ))}
        {finish && (
          <div className="step">
            <div className="row"><strong>{session.steps.length + 1}. Done</strong><JevBadge decision={finish} /></div>
            <Shadow decision={finish} />
          </div>
        )}
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

/** How likely Jev thought the step the LLM chose was, beside the LLM's own pick. */
function JevBadge({ decision: d }: { decision?: ShadowDecision }) {
  if (!d || d.error) return null;
  if (d.drove) {
    const p = d.probabilities[d.choice] ?? 0;
    return <span className="badge accent" title={`${d.model || "Jev"} chose this step; the LLM was not asked`}>chosen by Jev · p {p.toFixed(2)}</span>;
  }
  const p = d.probabilities[d.llm_choice] ?? 0;
  const agrees = d.choice === d.llm_choice;
  return (
    <span
      className={`badge ${agrees ? "good" : "warn"}`}
      title={`${d.model || "Jev"} gave ${label(d.llm_choice)} p ${p.toFixed(2)}; its own pick was ${label(d.choice)} (${(d.probabilities[d.choice] ?? 0).toFixed(2)})`}
    >
      Jev p {p.toFixed(2)}
    </span>
  );
}

/** What the System One model (Jev, gev) would have picked at this decision. */
function Shadow({ decision: d }: { decision?: ShadowDecision }) {
  if (!d) return null;
  if (d.error) return <div className="small" style={{ color: "var(--bad)" }}>{d.model || "Jev"}: {d.error}</div>;
  const top = Object.entries(d.probabilities).sort((a, b) => b[1] - a[1]).slice(0, 3);
  return (
    <div className="small">
      <span className={`badge ${d.drove ? "accent" : d.choice === d.llm_choice ? "good" : "warn"}`}>
        {d.model || "Jev"}: {label(d.choice)}
      </span>{" "}
      <span className="faint">
        {top.map(([k, p]) => `${label(k)} ${p.toFixed(2)}`).join(" · ")} · confidence {d.confidence.toFixed(2)} · {Math.round(d.latency_ms)} ms
      </span>
    </div>
  );
}

/** Whether the ambient filter thought this event mattered, before any LLM call. */
function AmbientFilterDetail({ decision: d }: { decision: NonNullable<Session["ambient_filter"]> }) {
  if (d.error) return <div className="small" style={{ color: "var(--bad)", marginBottom: 6 }}>{d.model || "Jev"} filter failed, ran anyway: {d.error}</div>;
  return (
    <div className="small" style={{ marginBottom: 6 }}>
      <span className={`badge ${d.skipped ? "" : "good"}`}>{d.model || "Jev"}: {d.skipped ? "does not matter, skipped" : "matters"}</span>{" "}
      <span className="faint">p {d.matters.toFixed(2)} (threshold {d.threshold}) · {Math.round(d.latency_ms)} ms</span>
    </div>
  );
}

function Candidates({ output }: { output: Record<string, unknown> }) {
  const candidates = output.candidates as AppSearchResult[];
  const reasons = (output.install_reasons ?? {}) as Record<string, string>;
  return (
    <div className="small" style={{ margin: "4px 0" }}>
      <span className="muted">searched {(output.app_queries as string[]).map((q) => `"${q}"`).join(", ")}:</span>
      <div className="row" style={{ flexWrap: "wrap", gap: 6, marginTop: 4 }}>
        {candidates.map((c) => (
          <span key={c.app_id} className={`badge ${reasons[c.app_id] ? "good" : ""}`} title={reasons[c.app_id] ?? c.summary}
            style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            <AppIcon listing={c} name={c.title} size={16} />
            {c.title}{reasons[c.app_id] ? " ✓" : ""}
          </span>
        ))}
      </div>
    </div>
  );
}
