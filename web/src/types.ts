// Shapes returned by GET /api/state (see quintessa/api/app.py).

export type NodeType =
  | "personal_preference" | "project_context" | "ambient_state" | "tool_knowledge"
  | "active_process" | "document" | "person" | "routine";

export interface MemoryNode {
  id: string; type: NodeType; title: string; body: string; topic_id: string | null;
  source_event_ids: string[]; created_at: string; updated_at: string;
}
export interface MemoryEdge { source_id: string; target_id: string; type: string; note: string; created_at: string }
export interface TriggerSpec { type: string; condition: string; reasoning: string; user_override: boolean }
export interface Topic {
  id: string; title: string; category: string; parent_id: string | null; summary: string; new_info: string;
  importance: string; progress: number; progress_note: string; due: string; triggers: TriggerSpec[];
  document_id: string | null; archived: boolean; last_seen_at: string | null; updated_at: string;
}
export interface DocumentSection {
  id: string; title: string; overview: string; status: string; details: string;
  actions_taken: string[]; suggested_actions: string[]; updated_at: string;
  /** good pictures of what the user chose in a question about this section */
  pictures?: Picture[];
}
/** A picture a tool returned: an image the app passed through or one found
 * on the web. With no url (nothing found), skins draw an illustration from
 * the emoji and caption. */
export interface Picture {
  id: string; caption: string; kind: "photo" | "thumbnail" | "logo" | "diagram"; url: string; emoji: string;
  width: number; height: number; source: string;
  /** where a real image is published, and who publishes it ("Wikimedia Commons") */
  page_url: string; credit: string;
}
export interface KeyDate { when: string; label: string; tentative: boolean }
export interface Doc {
  id: string; title: string; topic_id: string | null; description: string;
  status: "draft" | "active" | "waiting" | "complete" | "archived";
  progress_overview: string; sections: DocumentSection[]; links: string[]; key_dates: KeyDate[];
  observations: string[]; created_at: string; updated_at: string; pictures?: Picture[];
}
export interface ToolParameter { name: string; type: string; description: string; required: boolean }
export interface ToolFunction {
  name: string; description: string; parameters: ToolParameter[]; returns: string;
  oversight: "auto" | "auto_from_memory" | "confirm_once" | "always_ask"; long_running: boolean;
}
export interface AppListing {
  app_id: string; title: string; store: string; developer: string; icon_url: string; category: string;
  rating: number | null; store_url: string; summary: string;
}
export interface AppSearchResult extends AppListing { installed_as: string | null }
export interface Tool {
  name: string; description: string; kind: "builtin" | "llm" | "web_api" | "mcp" | "code" | "app";
  functions: ToolFunction[]; grounding: string; endpoint: string; code: string; created_by: string; created_at: string;
  listing: AppListing | null; binding: "simulated" | "mcp" | "web_api" | "android";
  auth: { kind: "none" | "oauth" | "api_key"; state: "simulated" | "needed" | "connected" };
}
export interface Permission {
  tool: string; function: string; granted: boolean; scope: string; detail: string;
  session_id: string | null; question_id: string | null; granted_at: string;
}
export interface Subscription {
  id: string; tool: string; function: string; description: string; stages: string[]; next_stage: number;
  document_id: string | null; section_id: string | null; archived: boolean; created_at: string;
}
export interface InputEvent {
  id: string; kind: string; content: string; source: string; device: string; sender: string;
  subscription_id: string | null; occurred_at: string;
}
export interface TraceStep {
  index: number; capability: string; focus: string; rationale: string; output: Record<string, unknown>;
  summary: string; model: string; error: string; started_at: string; ended_at: string | null; decided_by?: string;
}
export interface ShadowDecision {
  step_index: number; llm_choice: string; choice: string; probabilities: Record<string, number>;
  confidence: number; model: string; latency_ms: number; error: string; drove?: boolean;
}
export interface AmbientFilterDecision {
  matters: number; threshold: number; skipped: boolean; model: string; latency_ms: number; error: string;
}
export interface Session {
  id: string; trigger: InputEvent; status: "running" | "waiting_for_user" | "complete" | "failed" | "stopped";
  steps: TraceStep[]; permissions: Permission[]; shadow_decisions?: ShadowDecision[]; ambient_filter?: AmbientFilterDecision | null;
  pending_question_id: string | null; started_at: string; ended_at: string | null;
}
/** A picture and/or a quantity for one option of a choice field. */
export interface QuestionOption { option: string; picture: Picture | null; takes_quantity: boolean }
export interface QuestionField {
  name: string; kind: string; label: string; options: string[]; option_details?: QuestionOption[];
}
/** One option picked in a multi_option field, and how many. */
export interface Selection { option: string; quantity: number }
export interface Question {
  id: string; session_id: string; purpose: "disambiguation" | "permission" | "information" | "next_step"; prompt: string;
  fields: QuestionField[]; document_id: string | null; section_id: string | null; tool: string | null; function: string | null;
  topic_id: string | null; created_at: string;
  /** why the agent asks; for an approval, the arguments of the call it runs */
  context: string; arguments: Record<string, string>;
  /** asked by a session the user started moments ago: open it at once */
  user_waiting: boolean;
}
/** A waiting question the user put aside; its session still waits on it. */
export interface StashedQuestion { question_id: string; topic_id: string | null; stashed_at: string }
/** One tap starts it; the tap is the user's approval for this tool function. */
export interface CardAction {
  tool: string; function: string; label: string; arguments: Record<string, string>;
}
export interface Card {
  id: string; text: string; topic_id: string | null; document_id: string | null; section_id: string | null;
  question_id: string | null; urgency: string; detail: string; action: CardAction | null;
  /** when the card stops applying; when it was written; the event behind it (agent cards only) */
  expires_at?: string | null; created_at?: string; updated_at?: string; source_event_id?: string | null;
  due_at?: string | null; salience?: Salience;
}
/** Why a card ranks where it does (quintessa/device/salience.py); score orders the brief. */
export interface Salience {
  urgency: number | null; relevance: number; affinity: number; proximity: number; suppression: number;
  score: number; scored_by: string; scored_at: string | null;
}
/** The user pushed a card away (quintessa/device/salience.py). */
export interface Suppression { key: string; kind: "dismissed" | "snoozed"; at: string }
export type ViewMode = "focused" | "full";
export interface DocumentFocus {
  document_id: string; section_ids: string[]; mode: ViewMode; reason: string; set_by: string; updated_at: string;
}
/** Which parts of a document Spaces shows expanded (quintessa/device/focus.py). */
export interface DocView {
  document_id: string; section_ids: string[]; mode: ViewMode; reason: string;
  set_by: "agent" | "user" | "rule"; changed_section_ids: string[];
}
export interface DeviceState {
  island: { active: boolean; words: string };
  brief: Card[];
  snoozed: Card[];
  suppressions: Suppression[];
  open_question_ids: string[];
  stashed: StashedQuestion[];
  space_document_ids: string[];
  focused_document_id: string | null;
  focus: Record<string, DocumentFocus>;
  discovery: { title: string; reason: string; topic_id: string | null }[];
  notifications: string[];
}
export interface AmbientSource {
  id: string; name: string; kind: string; events: string[]; interval_seconds: number; speed: number;
  enabled: boolean; loop: boolean; device: string; sender: string; done: boolean;
}
export interface ModelSettings { chain: string[]; retries: number; base_delay: number; status: string }
export interface JevStatus {
  available: boolean; model: string; threshold: number | null; jev: boolean; jev_shadow: boolean; jev_filter: boolean; jev_drive: boolean; jev_rank: boolean;
}
export interface ModelProvider {
  provider: string; label: string; setup: string; models: { id: string; label: string }[];
}
export interface PersonaProfile {
  id: string; name: string; occupation: string; city: string; age: unknown; hobbies: unknown;
  goals_this_week: unknown; family: unknown; apps: unknown; image: string;
}
export interface AgentState {
  user_id: string;
  memory: {
    nodes: MemoryNode[]; edges: MemoryEdge[]; topics: Topic[]; documents: Doc[]; tools: Tool[];
    permissions: Permission[]; subscriptions: Subscription[]; events: InputEvent[]; sessions: Session[];
  };
  device: DeviceState;
  views: Record<string, DocView>;
  questions: Question[];
  ambient: { enabled: boolean; sources: AmbientSource[] };
  persona: { profile: PersonaProfile; date: string | null; running: boolean } | null;
  settings: ModelSettings;
  jev: JevStatus;
  apps: { store: string };
  server_time: string;
}
