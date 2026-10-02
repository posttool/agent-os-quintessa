import { useEffect, useState } from "react";
import type { Api } from "../api";
import type { AgentState } from "../types";
import { label, time } from "../format";

type Act = (fn: () => Promise<unknown>) => Promise<void>;
const KINDS = ["message", "notification", "location", "vision", "sensor", "screen", "speech", "text"];

export default function DataPanel({ state, api, act }: { state: AgentState; api: Api; act: Act }) {
  const [templates, setTemplates] = useState<{ name: string; kind: string; description: string }[]>([]);
  const [vibe, setVibe] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [custom, setCustom] = useState({ name: "", kind: "message", events: "", interval_seconds: 5 });
  useEffect(() => {
    api.templates().then(setTemplates, () => setTemplates([]));
  }, [api]);

  async function withBusy(key: string, fn: () => Promise<unknown>) {
    setBusy(key);
    await act(fn);
    setBusy(null);
  }

  const { enabled, sources } = state.ambient;
  const processes = state.memory.subscriptions;
  const events = [...state.memory.events].reverse().slice(0, 60);

  return (
    <div>
      <div className="section">
        <h3>
          Ambient emission
          <label className="row" style={{ textTransform: "none", letterSpacing: 0, fontWeight: 400 }}>
            <input type="checkbox" checked={enabled} onChange={(e) => act(() => api.setAmbient(e.target.checked))} />
            {enabled ? "on" : "off"}
          </label>
        </h3>
        {sources.length === 0 && <div className="empty">No ambient sources. Add one from a template below.</div>}
        {sources.map((s) => (
          <div className="card" key={s.id}>
            <div className="row">
              <strong>{s.name}</strong>
              <span className="badge">{label(s.kind)}</span>
              <span className="badge">{s.device}</span>
              {s.sender && <span className="faint small">from {s.sender}</span>}
              {s.done && <span className="badge good">finished</span>}
              <span className="grow" />
              <label className="row small muted" title="Emission speed">
                {s.speed}×
                <input type="range" min={0.25} max={10} step={0.25} value={s.speed}
                  onChange={(e) => act(() => api.patchSource(s.id, { speed: Number(e.target.value) }))} />
              </label>
              <label className="row small muted">
                <input type="checkbox" checked={s.enabled} onChange={(e) => act(() => api.patchSource(s.id, { enabled: e.target.checked }))} />
                on
              </label>
              <button className="danger" onClick={() => act(() => api.deleteSource(s.id))}>Remove</button>
            </div>
            <details className="small" style={{ marginTop: 4 }}>
              <summary className="muted">{s.events.length} events, every {s.interval_seconds}s at 1×</summary>
              <ol style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                {s.events.map((e, i) => <li key={i}>{e}</li>)}
              </ol>
            </details>
          </div>
        ))}
      </div>

      <div className="section">
        <h3>Add from template {state.persona && <span className="badge accent">grounded in {state.persona.profile.name}</span>}</h3>
        <div className="row">
          {templates.map((t) => (
            <button key={t.name} title={t.description} disabled={busy !== null}
              onClick={() => withBusy(t.name, () => api.addTemplate(t.name, 6))}>
              {busy === t.name ? "Writing…" : `+ ${label(t.name)}`}
            </button>
          ))}
        </div>
      </div>

      <div className="section">
        <h3>Vibe-code a source</h3>
        <div className="row">
          <input className="grow" placeholder="e.g. a flight that gets delayed and changes gate" value={vibe}
            onChange={(e) => setVibe(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && vibe.trim() && withBusy("vibe", async () => { await api.addVibe(vibe); setVibe(""); })} />
          <button className="primary" disabled={!vibe.trim() || busy !== null}
            onClick={() => withBusy("vibe", async () => { await api.addVibe(vibe); setVibe(""); })}>
            {busy === "vibe" ? "Writing…" : "Create"}
          </button>
        </div>
        <details style={{ marginTop: 8 }}>
          <summary className="muted small">or write one by hand</summary>
          <div className="card" style={{ marginTop: 8 }}>
            <div className="row">
              <input placeholder="name" value={custom.name} onChange={(e) => setCustom({ ...custom, name: e.target.value })} />
              <select value={custom.kind} onChange={(e) => setCustom({ ...custom, kind: e.target.value })}>
                {KINDS.map((k) => <option key={k}>{k}</option>)}
              </select>
              <label className="row small muted">every
                <input type="number" min={0} style={{ width: 60 }} value={custom.interval_seconds}
                  onChange={(e) => setCustom({ ...custom, interval_seconds: Number(e.target.value) })} />s
              </label>
            </div>
            <textarea rows={4} style={{ width: "100%", marginTop: 8 }} placeholder="one event per line"
              value={custom.events} onChange={(e) => setCustom({ ...custom, events: e.target.value })} />
            <div className="row" style={{ justifyContent: "flex-end", marginTop: 6 }}>
              <button disabled={!custom.name || !custom.events.trim()}
                onClick={() => act(async () => {
                  await api.addSource({ ...custom, events: custom.events.split("\n").map((l) => l.trim()).filter(Boolean) });
                  setCustom({ ...custom, name: "", events: "" });
                })}>
                Add source
              </button>
            </div>
          </div>
        </details>
      </div>

      <div className="section">
        <h3>Processes the agent is following</h3>
        {processes.length === 0 && <div className="empty">None. Long-running tool calls show up here.</div>}
        {processes.map((p) => (
          <div className="card" key={p.id}>
            <div className="row">
              <span className="grow">{p.description}</span>
              <span className={`badge ${p.archived ? "good" : "warn"}`}>{p.archived ? "complete" : `${p.next_stage}/${p.stages.length}`}</span>
            </div>
            <div className="row small" style={{ marginTop: 4 }}>
              {p.stages.map((s, i) => (
                <span key={i} className={`badge ${i < p.next_stage ? "accent" : ""}`}>{s}</span>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="section">
        <h3>Incoming events</h3>
        {events.length === 0 && <div className="empty">Nothing yet.</div>}
        {events.map((e) => (
          <div key={e.id} className="row small" style={{ padding: "3px 0", borderTop: "1px solid var(--border)", alignItems: "baseline" }}>
            <span className="faint mono">{time(e.occurred_at)}</span>
            <span className="badge">{label(e.kind)}</span>
            <span className="faint">{e.source}</span>
            <span className="grow">{e.sender && <strong>{e.sender}: </strong>}{e.content}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
