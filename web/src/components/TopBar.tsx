import { useEffect, useRef, useState } from "react";
import type { Api } from "../api";
import type { AgentState, PersonaProfile } from "../types";

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

function ModelSettings({ api, state, act, onClose }: Pick<Props, "api" | "act"> & { state: AgentState; onClose: () => void }) {
  const [chain, setChain] = useState(state.settings.chain.join("\n"));
  const [retries, setRetries] = useState(state.settings.retries);
  const [delay, setDelay] = useState(state.settings.base_delay);
  return (
    <div className="popover">
      <div className="field">
        <span>Model chain, tried in order (provider:model, one per line)</span>
        <textarea rows={4} value={chain} onChange={(e) => setChain(e.target.value)} />
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
        Examples: gemini:gemini-3.8-flash, gemini:gemini-2.5-flash, claude:claude-opus-5-5.
      </p>
      {state.settings.status && <p className="small" style={{ color: "var(--bad)" }}>{state.settings.status}</p>}
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <button onClick={onClose}>Close</button>
        <button
          className="primary"
          onClick={() =>
            act(async () => {
              await api.putSettings({ chain: chain.split("\n").map((c) => c.trim()).filter(Boolean), retries, base_delay: delay });
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
