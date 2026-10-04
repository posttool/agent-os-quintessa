import type { AgentState, AppListing, AppSearchResult, DocView, JevStatus, ModelProvider, ModelSettings, PersonaProfile, ViewMode } from "./types";

export class ApiError extends Error {}

export function makeApi(user: string) {
  const q = (path: string) => `${path}${path.includes("?") ? "&" : "?"}user=${encodeURIComponent(user)}`;

  async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
    const res = await fetch(q(path), {
      method,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : typeof body === "string" ? body : JSON.stringify(body),
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        detail = (await res.json()).detail ?? detail;
      } catch {
        /* not JSON */
      }
      throw new ApiError(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return res.json() as Promise<T>;
  }

  return {
    streamUrl: q("/api/stream"),
    exportUrl: q("/api/export"),
    state: () => call<AgentState>("GET", "/api/state"),
    input: (content: string, kind = "text") => call<{ session_id: string }>("POST", "/api/input", { content, kind }),
    answer: (id: string, values: Record<string, string>, dismissed = false) =>
      call("POST", `/api/questions/${encodeURIComponent(id)}`, { values, dismissed }),
    /** Put a question aside for later; it keeps waiting, out of the stack. */
    stash: (id: string) => call("POST", `/api/questions/${encodeURIComponent(id)}/stash`),
    unstash: (id: string) => call("POST", `/api/questions/${encodeURIComponent(id)}/unstash`),
    /** section_ids null drops the user's choice so the agent's focus returns. */
    view: (document_id: string, section_ids: string[] | null, mode: ViewMode = "focused") =>
      call<DocView>("POST", "/api/view", { document_id, section_ids, mode }),
    /** The user tapped a brief card's action; the tap approves that call. */
    cardAct: (cardId: string) => call<{ session_id: string }>("POST", `/api/cards/${encodeURIComponent(cardId)}/act`),
    cardOpen: (cardId: string) => call("POST", `/api/cards/${encodeURIComponent(cardId)}/open`),
    cardDismiss: (cardId: string) => call("POST", `/api/cards/${encodeURIComponent(cardId)}/dismiss`),
    cardSnooze: (cardId: string, minutes = 60) =>
      call("POST", `/api/cards/${encodeURIComponent(cardId)}/snooze?minutes=${minutes}`),
    seen: (topicId: string) => call("POST", `/api/topics/${encodeURIComponent(topicId)}/seen`),
    clear: () => call("POST", "/api/clear"),
    restore: (text: string) => call("POST", "/api/restore", text),
    putTool: (tool: unknown) => call("POST", "/api/tools", tool),
    deleteTool: (name: string) => call("DELETE", `/api/tools/${encodeURIComponent(name)}`),
    templates: () => call<{ name: string; kind: string; description: string }[]>("GET", "/api/ambient/templates"),
    setAmbient: (enabled: boolean) => call("PUT", "/api/ambient/enabled", { enabled }),
    addSource: (source: unknown) => call("POST", "/api/ambient/sources", source),
    addTemplate: (template: string, count: number) => call("POST", "/api/ambient/sources/from-template", { template, count }),
    addVibe: (description: string) => call("POST", "/api/ambient/sources/vibe", { description }),
    patchSource: (id: string, patch: { speed?: number; enabled?: boolean }) =>
      call("PATCH", `/api/ambient/sources/${id}`, patch),
    deleteSource: (id: string) => call("DELETE", `/api/ambient/sources/${id}`),
    personas: () => call<PersonaProfile[]>("GET", "/api/personas"),
    startPersona: (persona_id: string, speed: number) => call("POST", "/api/persona/start", { persona_id, speed }),
    stopPersona: () => call("POST", "/api/persona/stop"),
    putSettings: (s: Omit<ModelSettings, "status">) => call<ModelSettings>("PUT", "/api/settings", s),
    models: () => call<ModelProvider[]>("GET", "/api/models"),
    /** null returns a setting to the platform default. */
    searchApps: (q: string) => call<AppSearchResult[]>("GET", `/api/apps/search?q=${encodeURIComponent(q)}`),
    installApp: (listing: AppListing) => call("POST", "/api/apps/install", listing),
    uninstallApp: (appId: string) => call("DELETE", `/api/apps/${encodeURIComponent(appId)}`),
    putPreferences: (p: Partial<Record<"jev" | "jev_shadow" | "jev_filter" | "jev_drive" | "jev_rank", boolean | null>>) =>
      call<JevStatus>("PUT", "/api/preferences", p),
  };
}

export type Api = ReturnType<typeof makeApi>;
