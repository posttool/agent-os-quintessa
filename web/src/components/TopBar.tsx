import { useEffect, useRef, useState } from "react";
import type { Api } from "../api";
import type { AgentState, ModelProvider, PersonaProfile } from "../types";

interface Props {
  api: Api;
  state: AgentState | null;
  user: string;
  onUser: (u: string) => void;
  theme: string;
  onTheme: (t: string) => void;
  connected: boolean;
  act: (fn: () => Promise<unknown>) => Promise<void>;
}

export default function TopBar({ api, state, user, onUser, theme, onTheme, connected, act }: Props) {
  const [draftUser, setDraftUser] = useState(user);
  const [showModels, setShowModels] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  useEffect(() => setDraftUser(user), [user]);

  const isDark =
    theme === "dark" || (!theme && window.matchMedia?.("(prefers-color-scheme: dark)").matches);

  async function restoreFile(file: File) {
    await act(async () => {
      await api.restore(await file.text());
    });
  }

  return (
    <header className="topbar">
      <div className="brand">
        Quint<span>essa</span>
      </div>
      <label title={connected ? "live" : "reconnecting"}>
        <span className={`dot ${connected ? "on" : ""}`} />
        user
        <input
          style={{ width: 130 }}
          value={draftUser}
          onChange={(e) => setDraftUser(e.target.value)}
          onBlur={() => draftUser.trim() && onUser(draftUser.trim())}
          onKeyDown={(e) => e.key === "Enter" && draftUser.trim() && onUser(draftUser.trim())}
        />
      </label>
      <PersonaPicker api={api} state={state} act={act} />
      <div className="spacer" />
      {state && <JevToggle api={api} state={state} act={act} />}
      <div style={{ position: "relative" }}>
        <button onClick={() => setShowModels((v) => !v)}>
          Model: {state?.settings.chain[0]?.split(":")[1] ?? "…"}
          {state?.settings.status ? " ⚠" : ""}
        </button>
        {showModels && state && <ModelSettings api={api} state={state} act={act} onClose={() => setShowModels(false)} />}
      </div>
      <a href={api.exportUrl} download>
        <button>Download state</button>
      </a>
      <button onClick={() => fileInput.current?.click()}>Restore…</button>
      <input
        ref={fileInput}
        type="file"
        accept="application/json,.json"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (f && confirm(`Replace ${user}'s agent state with ${f.name}?`)) void restoreFile(f);
        }}
      />
      <button
        className="danger"
        onClick={() => confirm(`Clear all memory, traces, tools and data for ${user}?`) && act(api.clear)}
      >
        Clear memory
      </button>
      <button className="ghost" title="Toggle theme" onClick={() => onTheme(isDark ? "light" : "dark")}>
        {isDark ? "☀︎" : "☾"}
      </button>
    </header>
  );
}

function PersonaPicker({ api, state, act }: Pick<Props, "api" | "state" | "act">) {
  const [people, setPeople] = useState<PersonaProfile[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [choice, setChoice] = useState("");
  const [speed, setSpeed] = useState(600);

  useEffect(() => {
    api.personas().then(setPeople, (e) => setError(String(e.message ?? e)));
  }, [api]);

  const running = state?.persona?.running;
  return (
    <label title={error ?? "Walk through a day in the life of an Aura persona"}>
      persona
      <select value={choice} onChange={(e) => setChoice(e.target.value)} disabled={!people?.length}>
        <option value="">{error ? "unavailable" : people ? "choose…" : "loading…"}</option>
        {people?.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name} · {String(p.occupation)}
          </option>
        ))}
      </select>
      <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))} title="Simulated seconds per real second">
        {[60, 600, 3600].map((s) => (
          <option key={s} value={s}>
            {s}×
          </option>
        ))}
      </select>
      {running ? (
        <button onClick={() => act(api.stopPersona)}>Stop {state?.persona?.profile.name}</button>
      ) : (
        <button
          disabled={!choice}
          onClick={() =>
            confirm("Starting a persona clears this user's memory, tools and data. Continue?") &&
            act(() => api.startPersona(choice, speed))
          }
        >
          Start day
        </button>
      )}
    </label>
  );
}

/** Turns the System One model (Jev, gev) on or off for this user. */
function JevToggle({ api, state, act }: Pick<Props, "api" | "act"> & { state: AgentState }) {
  const [open, setOpen] = useState(false);
  const jev = state.jev;
  const set = (p: Parameters<typeof api.putPreferences>[0]) => act(() => api.putPreferences(p));
  const title = jev.available
    ? `${jev.model}: next step ${jev.jev_drive ? "chosen by Jev" : `shadow ${jev.jev_shadow ? "on" : "off"}`}, ambient filter ${jev.jev_filter ? "on" : "off"}`
    : "Jev is not configured on the server (set QUINTESSA_JEV_API_KEY)";
  return (
    <div style={{ position: "relative" }} className="row">
      <label title={title}>
        <input type="checkbox" checked={jev.available && jev.jev} disabled={!jev.available} onChange={(e) => set({ jev: e.target.checked })} />
        Jev
      </label>
      <button className="ghost" title="Jev options" onClick={() => setOpen((v) => !v)}>▾</button>
      {open && (
        <div className="popover">
          {!jev.available && <p className="small" style={{ color: "var(--warn)", marginTop: 0 }}>{title}.</p>}
          <label className="check">
            <input type="checkbox" checked={jev.jev} disabled={!jev.available} onChange={(e) => set({ jev: e.target.checked })} />
            <span><strong>Use Jev</strong> {jev.model && <span className="faint">({jev.model})</span>}</span>
          </label>
          <label className="check">
            <input type="checkbox" checked={jev.jev_shadow} disabled={!jev.available || !jev.jev || jev.jev_drive} onChange={(e) => set({ jev_shadow: e.target.checked })} />
            <span>Shadow next steps: ask Jev beside the LLM and show its probability in Traces (never followed)</span>
          </label>
          <label className="check">
            <input type="checkbox" checked={jev.jev_drive} disabled={!jev.available || !jev.jev} onChange={(e) => set({ jev_drive: e.target.checked })} />
            <span>Let Jev choose the next step instead of the LLM (the LLM takes over when Jev fails)</span>
          </label>
          <label className="check">
            <input type="checkbox" checked={jev.jev_filter} disabled={!jev.available || !jev.jev} onChange={(e) => set({ jev_filter: e.target.checked })} />
            <span>Skip ambient events Jev says do not matter{jev.threshold != null && ` (p < ${jev.threshold})`}</span>
          </label>
          <label className="check">
            <input type="checkbox" checked={jev.jev_rank} disabled={!jev.available || !jev.jev} onChange={(e) => set({ jev_rank: e.target.checked })} />
            <span>Let Jev score brief cards (urgency, fits now, person) to rank the brief</span>
          </label>
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <button onClick={() => set({ jev: null, jev_shadow: null, jev_filter: null, jev_drive: null, jev_rank: null })} title="Use the server's defaults">Reset</button>
            <button onClick={() => setOpen(false)}>Close</button>
          </div>
        </div>
      )}
    </div>
  );
}

const OTHER = "__other__";

function ModelSettings({ api, state, act, onClose }: Pick<Props, "api" | "act"> & { state: AgentState; onClose: () => void }) {
  const [chain, setChain] = useState<string[]>(state.settings.chain);
  const [retries, setRetries] = useState(state.settings.retries);
  const [delay, setDelay] = useState(state.settings.base_delay);
  const [catalog, setCatalog] = useState<ModelProvider[]>([]);
  useEffect(() => {
    api.models().then(setCatalog, () => setCatalog([]));
  }, [api]);

  const known = new Set(catalog.flatMap((p) => p.models.map((m) => m.id)));
  const update = (i: number, value: string) => setChain((c) => c.map((v, j) => (j === i ? value : v)));
  return (
    <div className="popover">
      <div className="field">
        <span>Model chain, tried in order: the first is used, the rest are fallbacks</span>
        {chain.map((value, i) => {
          const custom = !known.has(value);
          return (
            <div key={i} className="row" style={{ flexWrap: "nowrap" }}>
              <span className="faint small mono" style={{ width: 14 }}>{i + 1}</span>
              <select className="grow" style={{ minWidth: 0 }} value={custom ? OTHER : value} onChange={(e) => update(i, e.target.value === OTHER ? "" : e.target.value)}>
                {catalog.map((p) => (
                  <optgroup key={p.provider} label={p.setup ? `${p.label} (${p.setup})` : p.label}>
                    {p.models.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                  </optgroup>
                ))}
                <option value={OTHER}>Other (provider:model)…</option>
              </select>
              {custom && (
                <input className="grow" style={{ minWidth: 0 }} placeholder="provider:model" value={value} onChange={(e) => update(i, e.target.value)} />
              )}
              <button className="ghost" title="Remove" disabled={chain.length === 1} onClick={() => setChain((c) => c.filter((_, j) => j !== i))}>×</button>
            </div>
          );
        })}
        <div>
          <button className="ghost" onClick={() => setChain((c) => [...c, catalog[0]?.models[0]?.id ?? ""])}>+ Add fallback</button>
        </div>
      </div>
      <div className="row">
        <label className="field grow">
          <span>Retries per model</span>
          <input type="number" min={0} max={6} value={retries} onChange={(e) => setRetries(Number(e.target.value))} />
        </label>
        <label className="field grow">
          <span>First backoff (s), doubles each retry</span>
          <input type="number" min={0} step={0.5} value={delay} onChange={(e) => setDelay(Number(e.target.value))} />
        </label>
      </div>
      <p className="small muted" style={{ margin: "0 0 10px" }}>
        Transient errors and bad output retry the same model; refusals and hard errors fall back to the next.
      </p>
      {state.settings.status && <p className="small" style={{ color: "var(--bad)" }}>{state.settings.status}</p>}
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <button onClick={onClose}>Close</button>
        <button
          className="primary"
          onClick={() =>
            act(async () => {
              await api.putSettings({ chain: chain.map((c) => c.trim()).filter(Boolean), retries, base_delay: delay });
              onClose();
            })
          }
        >
          Apply
        </button>
      </div>
    </div>
  );
}
