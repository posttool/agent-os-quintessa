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
  actions_taken: string[]; suggested_actions: string[]; process_ids: string[]; updated_at: string;
}
export interface KeyDate { when: string; label: string; tentative: boolean }
export interface Doc {
  id: string; title: string; topic_id: string | null; description: string;
  status: "draft" | "active" | "waiting" | "complete" | "archived";
  progress_overview: string; sections: DocumentSection[]; links: string[]; key_dates: KeyDate[];
  observations: string[]; created_at: string; updated_at: string;
}
export interface ToolParameter { name: string; type: string; description: string; required: boolean }
export interface ToolFunction {
  name: string; description: string; parameters: ToolParameter[]; returns: string;
  oversight: "auto" | "auto_from_memory" | "confirm_once" | "always_ask"; long_running: boolean;
}
export interface Tool {
  name: string; description: string; kind: "builtin" | "llm" | "web_api" | "mcp" | "code";
  functions: ToolFunction[]; grounding: string; endpoint: string; code: string; created_by: string; created_at: string;
}
export interface Permission {
  tool: string; function: string; granted: boolean; scope: string; detail: string;
  session_id: string | null; ux_request_id: string | null; granted_at: string;
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
  summary: string; model: string; error: string; started_at: string; ended_at: string | null;
}
export interface ShadowDecision {
  step_index: number; llm_choice: string; choice: string; probabilities: Record<string, number>;
  confidence: number; model: string; latency_ms: number; error: string;
}
export interface Session {
  id: string; trigger: InputEvent; status: "running" | "waiting_for_user" | "complete" | "failed" | "stopped";
  steps: TraceStep[]; permissions: Permission[]; shadow_decisions?: ShadowDecision[];
  pending_ux_id: string | null; started_at: string; ended_at: string | null;
}
export interface UXField { name: string; kind: string; label: string; options: string[] }
export interface UXRequest {
  id: string; session_id: string; purpose: "disambiguation" | "permission" | "information"; prompt: string;
  fields: UXField[]; document_id: string | null; section_id: string | null; tool: string | null; function: string | null;
  created_at: string;
}
export interface BriefItem {
  text: string; topic_id: string | null; document_id: string | null; section_id: string | null;
  ux_request_id: string | null; urgency: string;
}
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
  brief: BriefItem[];
  open_ux_ids: string[];
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
  pending_ux: UXRequest[];
  ambient: { enabled: boolean; sources: AmbientSource[] };
  persona: { profile: PersonaProfile; date: string | null; running: boolean } | null;
  settings: ModelSettings;
  server_time: string;
}
