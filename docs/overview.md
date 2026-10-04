# Quintessa: system overview

Quintessa is a personal agent operating system. An LLM-driven reasoning loop works over a memory of the user's world, and a device surface shows the user what matters right now.

This document is the up-to-date version of the first brief ([spec.md](spec.md)). It describes what the system does today, as of PR #21, and uses one name for each idea. The [glossary](#glossary) at the end lists those names and the older words they replace. Schemas are taken from the code (`quintessa/models/`, `quintessa/device/`) and show field names exactly as they are stored and sent by the API.

Ideas from the first brief that are not built yet are listed in [Not built yet](#not-built-yet).

## Contents

1. [Principles](#principles)
2. [The big picture](#the-big-picture)
3. [Inputs and reasoning sessions](#inputs-and-reasoning-sessions)
4. [Capabilities](#capabilities)
5. [Memory](#memory)
6. [Topics](#topics)
7. [Documents](#documents)
8. [Questions](#questions)
9. [Tools and apps](#tools-and-apps)
10. [Processes](#processes)
11. [The device](#the-device)
12. [The contextual brief](#the-contextual-brief)
13. [Spaces and document focus](#spaces-and-document-focus)
14. [System One decision models (Jev)](#system-one-decision-models-jev)
15. [Ambient data and personas](#ambient-data-and-personas)
16. [Per-user state, storage and the API](#per-user-state-storage-and-the-api)
17. [The web app](#the-web-app)
18. [Not built yet](#not-built-yet)
19. [Glossary](#glossary)

## Principles

These come from the first brief and still hold.

- **The LLM does the reasoning.** Every model call returns JSON that matches a closed schema. Code only carries out those structured decisions; it never uses string parsing, regular expressions or fixed text to decide anything.
- **Capabilities are markdown files.** The set of reasoning capabilities is configurable, and each one is a markdown file the loop loads.
- **One dataclass or enum per file**, in `quintessa/models/`.
- **Memory knows nothing about design.** Memory and reasoning never reference a skin or a screen. Surfaces subscribe to changes, and the same agent can be reached from any device through the API.
- **Bootstrap data lives in separate files** (`quintessa/samples/`): tool suggestions, ambient source templates and the offline app catalog. Nothing is preloaded; every user starts with a blank slate.
- **Per-user, durable state.** There is no global memory. Each user has their own agent, saved as it changes, with download and restore.

## The big picture

```
input event (text, speech, message, location, vision, process progress, ...)
   │
   ▼
AgentHost ──► the user's agent (AgentRuntime, loaded from storage on first use)
   │
   ▼
reasoning session (one per input event; many run at once)
   │  each step the controller picks ONE capability, or "done"
   ├─ memory          read, write and organize the graph, topics and documents
   ├─ generative_ui   ask the user a question; the session waits for the answer
   ├─ tool_discovery  find and install an app, or define a tool
   └─ tool_use        call one tool function (web, device, apps, agent-made tools)
   │
   ▼
memory (MemoryStore)                 device surface (DeviceSurface)
graph, topics, documents, tools,     island, brief, Spaces, Discover,
permissions, processes, traces       notifications
   │                                   │
   └──────── listeners ────────────────┴──► saved state, live web app
```

## Inputs and reasoning sessions

Anything that happens to the user is an **input event**. Each input event starts one **reasoning session**: a run of the reasoning loop (`AgentReasoningLoop`) for that event. Many sessions run at once over the same user's memory, and a session waiting on the user never blocks the others.

```ts
InputEvent {
  id: string                 // "evt_..."
  kind: "text" | "speech" | "message" | "location" | "vision" | "screen"
      | "notification" | "sensor" | "process_progress"
  content: string
  source: string             // "user", "ambient:<source name>", "persona", "process:<tool>"
  device: string             // "phone", ...
  sender: string             // who sent a message, when there is one
  subscription_id: string | null   // set on process progress
  occurred_at: string        // ISO time
}
```

Input events are kept in memory for audit only. Memory organizes what they mean; it does not file the raw events.

### Steps

A session is a sequence of **steps**. Before each step the **controller** (one model call, prompt in `capabilities/_controller.md`) reads the context and picks one capability with a `focus` (exactly what to do) and a few **status words** for the dynamic island, or picks `done`. The capability runs, and its summary joins the context for the next decision. A session ends at `done` or after 12 steps.

What the controller reads is built in one place (`executors/common.py: controller_context`), so the LLM and Jev decide from the same facts:

```ts
ControllerContext {
  capabilities: { name, description }[]
  now: string
  trigger: InputEvent
  steps_so_far: { capability, focus, summary, error }[]
  session_permissions: Permission[]
  memory: MemorySnapshot          // see Memory; archived topics and documents left out
  on_screen: DocumentView | null  // what Spaces shows now
  brief: BriefCardContext[]       // the brief as it stands, with a `stale` reason per card
  questions_waiting: { id, prompt, topic_id, asked_at, stashed }[]
  max_steps_left: number
}
```

After the last step the session runs two housekeeping steps when needed: the **brief refresh** (see [The contextual brief](#the-contextual-brief)) and, when Jev scoring is on, **brief scoring**.

### Sessions and traces

The session record is the **trace**: every step, with what was decided, by whom, what the capability returned and which model answered.

```ts
ReasoningSession {
  id: string                 // "ses_..."
  trigger: InputEvent
  status: "running" | "waiting_for_user" | "complete" | "failed" | "stopped"
  steps: TraceStep[]
  permissions: Permission[]  // grants given in this session; they carry forward to later steps
  shadow_decisions: ShadowDecision[]   // Jev's picks beside the LLM's (see Jev)
  prefilter: PrefilterDecision | null  // Jev's "does this matter?" for ambient events
  pending_ux_id: string | null         // the question this session is waiting on
  started_at: string
  ended_at: string | null
}

TraceStep {
  index: number
  capability: string         // a capability name, or "brief_refresh" / "brief_rank"
  focus: string
  rationale: string
  output: object             // the capability's structured result
  summary: string
  model: string              // the model that answered
  error: string
  decided_by: string         // "jev" when Jev picked the step, "" when the LLM did
  started_at: string
  ended_at: string | null
}
```

### Resilience

`ResilientLLM` retries a model on transient errors and on output that does not match the schema, with backoff, then falls back along the **model chain**: a list of `provider:model` pairs (Claude on the Anthropic API or Vertex, Gemini on Vertex). The default chain is `gemini:gemini-3.8-flash,gemini:gemini-2.5-flash`. A session that runs out of models is marked `failed` with the error in its last step, and the other sessions keep running.

## Capabilities

A **capability** is a markdown file in `quintessa/capabilities/`. Its front matter names the **executor** (the code that applies the model's output) and a `choose_when` criterion (what Jev reads when it picks the next step). Its body is the system prompt for that capability's model call.

```ts
Capability {
  name: string
  description: string
  executor: string           // memory | generative_ui | tool_discovery | tool_use
  instructions: string       // the file body
  choose_when: string
}
```

The four capabilities today:

| Capability | What it does | Executor result |
|---|---|---|
| `memory` | Merges what the trigger means into the graph, topics and documents; deletes what is out of date; retrieves facts a task needs. | A list of memory operations (see below) and a summary. |
| `generative_ui` | Asks the user one clear question with generated UI, then the session waits. | A question (`UXRequest`); the answer resumes the step. |
| `tool_discovery` | Equips the agent: reuses an installed tool, or searches an app store and installs an app, or defines a tool when no app fits. Two model calls: plan (queries), then choose (from store candidates). | Installed apps, defined tools, uninstalled apps. |
| `tool_use` | Calls exactly one function of one tool, gated by its oversight level; can start a process. | The call, its result and any process subscription. |

The capability set is configurable with `load_capabilities(dir, names=[...])`.

## Memory

**Memory** (`MemoryStore`) is everything one user's agent knows. It holds:

- the **graph**: nodes and edges, the facts about the user's world;
- the **topic index**: topics, the organized view of what the user cares about;
- **documents**: the progressively built record of each topic;
- **tools** the agent can use, and **permissions** the user granted;
- **process subscriptions** for long-running tool calls;
- **input events** (for audit) and **sessions** (the traces).

Memory emits a change for every write; the device, the saved state and the web app listen.

### The graph

```ts
MemoryNode {
  id: string                 // a readable slug the model chooses, e.g. "pref-food-thai"
  type: "personal_preference" | "project_context" | "ambient_state" | "tool_knowledge"
      | "active_process" | "document" | "person" | "routine"
  title: string
  body: string
  topic_id: string | null
  source_event_ids: string[] // which input events this came from
  created_at: string
  updated_at: string
}

MemoryEdge {                 // keyed by (source_id, target_id, type); edges have no id
  source_id: string
  target_id: string
  type: "relates_to" | "executing_for" | "part_of" | "depends_on"
      | "conflicts_with" | "supersedes" | "mentions"
  note: string
  created_at: string
}
```

### Memory operations

The `memory` capability never edits memory directly. It returns a list of operations, and `memory/apply.py` carries them out. Each operation fills only the object its `op` needs.

| `op` | Reads | Effect |
|---|---|---|
| `upsert_node`, `delete_node` | `node` / `id` | Add, merge or delete a node (deleting a node drops its edges). |
| `upsert_edge`, `delete_edge` | `edge` | Add or delete a relationship. |
| `upsert_topic`, `archive_topic` | `topic` / `id` | Add or update a topic; archive one whose time has passed. |
| `mark_topic_seen` | `id` | Clear "new since last seen" without changing what the topic says. |
| `upsert_document`, `archive_document` | `document` / `id` | Add or update a document; archive it when its process is complete. |
| `upsert_section` | `section` | Add or update one section of a document. |

Delete and archive operations carry a `reason`, which shows in the trace.

### What the model sees

Every capability call and every controller call gets a **memory snapshot**: nodes, edges, topics and documents (archived ones left out), tools (without their call history), permissions and active processes. Today the whole snapshot goes into each prompt; there is no retrieval step yet.

## Topics

A **topic** is one entry in the **topic index**, the organized view of the user's world: "Dinner plans", "Math test prep", "New sofa". Topics nest with `parent_id` (a "Pick a place" subtopic under "Dinner plans"), and categories are free text, so the user or the agent can add a new one at any time.

A topic carries the metadata the agent uses to decide when and how to surface it: trigger rules, a summary and what is new since the user last looked, progress and when it is due.

```ts
Topic {
  id: string
  title: string
  category: string           // free text: "Academics", "To dos", ...
  parent_id: string | null
  summary: string
  new_info: string           // what changed since the user last looked; "" once seen
  importance: string         // free text, e.g. "top priority on weekdays"
  progress: number           // 0 to 1
  progress_note: string
  due: string                // free text, e.g. "Before 6/26/2026", "Next week"
  triggers: TriggerSpec[]
  document_id: string | null
  archived: boolean
  last_seen_at: string | null
  updated_at: string
}

TriggerSpec {                // when the topic should surface
  type: "time" | "location" | "activity" | "observation"
  condition: string          // "at the grocery store", "the day before the party"
  reasoning: string          // why the agent chose this default
  user_override: boolean     // set by the user; wins over the agent's defaults
}
```

How the brief's ideas map to these fields:

| First brief | Today |
|---|---|
| Trigger types & trigger reasoning | `triggers[].type`, `condition`, `reasoning` |
| User triggering overrides | `triggers[].user_override`, `importance` |
| Summary & "new since last seen" | `summary`, `new_info`, `last_seen_at` (cleared when the user opens the topic's card or document) |
| Progress | `progress`, `progress_note` |
| Due dates | `due` on the topic; exact dates as `key_dates` on its document |
| Old entries | `archived` (the memory capability archives topics whose dates have passed) |

The topic index (maintaining what is known) is kept separate from the brief (reducing it to what matters now), as the first brief suggested.

## Documents

A **document** is the progressively built record of one topic's lifecycle: a dinner delivery, a trip, a semester of homework. It starts small and grows as the agent and the user act. It carries the live status of processes it started, their results and the follow-up actions. When the topic's process is complete and nothing is owed, the agent archives it.

```ts
Document {
  id: string
  title: string              // "Math test prep"
  topic_id: string | null
  description: string        // "Get proficient on the topics for the upcoming quiz."
  status: "draft" | "active" | "waiting" | "complete" | "archived"
  progress_overview: string
  sections: DocumentSection[]
  links: string[]            // useful apps, sites, other documents
  key_dates: KeyDate[]
  observations: string[]     // "Message from Jerry: Did you finish the homework?"
  created_at: string
  updated_at: string
}

DocumentSection {
  id: string
  title: string              // "Substitution"
  overview: string
  status: string             // free text: "complete", "needs attention", ...
  details: string
  actions_taken: string[]    // tool calls write a line here automatically
  suggested_actions: string[]
  updated_at: string         // drives "changed since you last looked"
}

KeyDate {
  when: string               // "5/29/2026 4pm"
  label: string              // "Test in testing center 4A"
  tentative: boolean         // "penciled in" until the user confirms
}
```

The math test example from the first brief maps directly: title, description, progress overview, one section per subtopic with its status and actions taken, links, key dates and relevant observations.

## Questions

When only the user can settle something, the agent asks a **question**: generated UI that the session waits on. The answer goes back to the context that asked (a document section, a pending tool call), so the session continues where it left off.

There are three kinds, by `purpose`:

- `disambiguation`: the agent is unsure what the user means or wants, or a choice has no basis in memory (a color, a restaurant).
- `information`: the agent needs a fact it does not have.
- `permission`: a tool function needs the user's approval (spending money, messaging someone). This kind is also called a **permission prompt**; `tool_use` creates one automatically when a function's oversight level requires it.

```ts
UXRequest {                  // a question
  id: string                 // "ux_..."
  session_id: string         // the session waiting on it
  purpose: "disambiguation" | "permission" | "information"
  prompt: string
  fields: UXField[]
  document_id: string | null // the context it returns to
  section_id: string | null
  tool: string | null        // for a permission: the function it authorizes
  function: string | null
  topic_id: string | null    // so the brief and sheets can show it with its topic
  context: string            // why the agent asks, one sentence, shown under the question
  arguments: { [name]: string }  // for a permission: the call it would run
  user_waiting: boolean      // asked by a session the user started in the last 2 minutes; the skin opens it at once
  created_at: string
}

UXField {                    // design-system-agnostic; the skin decides how to draw it
  name: string
  kind: "display_text" | "free_text" | "option" | "suggestion" | "number"
      | "location" | "confirm" | "button"
  label: string
  options: string[]
}

UXResponse {                 // the answer
  request_id: string
  values: { [field name]: string }   // a confirm field sends "yes" to approve
  dismissed: boolean                 // the user chose "Skip"; the session goes on without it
  surface_context: string            // where it was answered; "withdrawn: <reason>" when the agent took it back
  answered_at: string
}
```

What happens when a question is asked and answered:

1. The session's status becomes `waiting_for_user`, the island says "Waiting for you", and the question joins the stack at the top of the brief. Where it belongs to a document, Spaces shows a "Waiting on you" row in its place.
2. The user answers in the question sheet (`POST /api/ux/{id}`). The waiting session resumes with the values, and the device closes the form and returns to the document section the question came from.
3. If the session asks another question, the same thing happens again, until the session is done.

A question can also be **withdrawn**: when a later session changes the question's topic, the brief refresh may decide the news already answers it. The waiting session then resumes as if the question were dismissed, and is told why.

### Permissions

```ts
Permission {
  tool: string
  function: string
  granted: boolean
  scope: "session" | "persistent"
  detail: string             // what the user approved, e.g. the prompt
  session_id: string | null
  ux_request_id: string | null
  granted_at: string
}
```

A grant given in a session carries forward to every later step of that session, so the user is never asked twice in one session. A decline also carries forward: the call is skipped. A grant for a `confirm_once` function is also saved in memory with scope `persistent`, so later sessions do not ask again.

### The question sheet

Every question is answered in one place, the **question sheet**: a bottom sheet holding a **deck** of the waiting questions. The top question is full size with the next two peeking behind it ("1 of N"); answering, skipping or stashing it brings up the next, and a sideways swipe moves through the deck without answering. Option fields offer "Something else…" for a typed answer.

- The brief shows waiting questions as one **stack** at its top, oldest first; tapping it, a "Waiting on you" row, or the dynamic island opens the deck.
- A question from a session the user started moments ago (`user_waiting`) opens the sheet by itself, since they are likely still looking.
- **Skip** answers with `dismissed`, and the session goes on without the answer. Closing the sheet leaves the question waiting.
- **Stash** puts a question aside: it stays unanswered and its session keeps waiting, but it leaves the stack for an "N stashed questions" chip at the end of the brief, and the agent does not ask it again. A stashed question comes back to the stack when its topic changes after it was stashed.

```ts
StashedQuestion { ux_request_id: string, topic_id: string | null, stashed_at: string }
```

The prompts tell the agent never to ask in a notification, a card's text or a Discover item, where the user cannot answer.

## Tools and apps

A **tool** is a group of typed **functions** plus how the agent may use them. Every function has an **oversight level**.

```ts
Tool {
  name: string
  description: string
  kind: "builtin" | "llm" | "web_api" | "mcp" | "code" | "app"
  functions: ToolFunction[]
  grounding: string          // system prompt for llm tools
  endpoint: string           // URL for web_api and mcp tools
  code: string               // source for code tools
  created_by: string         // "system", "agent" or "user"
  listing: AppListing | null // app tools: what the store said
  binding: "simulated" | "mcp" | "web_api" | "android"   // app tools: how calls run
  auth: { kind: "none" | "oauth" | "api_key", state: "simulated" | "needed" | "connected" }
  history: ToolCallRecord[]  // recent calls to a simulated tool (last 30)
  created_at: string
}

ToolFunction {
  name: string
  description: string
  parameters: { name, type, description, required }[]
  returns: string
  oversight: "auto" | "auto_from_memory" | "confirm_once" | "always_ask"
  long_running: boolean      // starts a real-world process
}
```

Oversight levels, from least to most:

| Level | Meaning |
|---|---|
| `auto` | Run without asking. |
| `auto_from_memory` | Run, filling arguments from memory. |
| `confirm_once` | Ask the first time; a grant is kept in memory. |
| `always_ask` | Needs a grant in the current session (spending money, messaging someone). |

A tool call returns a **tool result**: `{ status: "done" | "in_progress" | "needs_user" | "failed", result, progress_stages }`.

### Built-in tools

There are two, as the first brief asked:

- **`web`**: `search` (Gemini's Google Search grounding, or Claude's web search tool), `fetch` (read a page as text) and `download` (save a file to the user's own downloads folder).
- **`device`**: how the agent changes what the user sees. `set_brief`, `update_brief`, `show_document`, `add_discovery` and `notify`. See [The device](#the-device).

### Apps

When the user wants something done that people do in a phone app (book a table, order food, get a ride), `tool_discovery` searches an **app store**, picks an app (one the user is known to use first) and installs it. A model writes the app's functions and oversight levels from its store listing. An installed **app** is a tool of kind `app` in that user's memory, and only installed tools can be called.

```ts
AppListing {
  app_id: string             // the store's id, e.g. a Play package name "com.opentable"
  title: string
  store: string              // "play", "search" or "offline"
  developer: string
  icon_url: string
  category: string
  rating: number | null
  store_url: string
  summary: string
}
```

The store is set by `QUINTESSA_APP_STORE`: Google Play (with icons), web search limited to Play listings, a bundled catalog of 44 apps, or `auto` (each in turn).

Every app is **simulated** today: a model grounded in the listing plays the app, keeping the last calls in `history` so it answers consistently, and sign-in is skipped. Code decides before each call whether it runs into a realistic problem (sold out, no driver, payment declined), about one call in five by default (`QUINTESSA_SIM_FAILURE_RATE`). The other bindings and auth states are recorded for when real apps arrive.

Agent-defined tools run by kind: `web_api` tools make a real HTTP request; `llm`, `mcp` and `code` tools are played by a model grounded in the tool's description, since nothing can run MCP or agent-written code yet.

The agent installs apps without asking, and never asks which app or service to use: it picks one (an app memory says the user uses, otherwise the best-known one) and only asks about details of the task. Installing never grants an app's risky functions; those still go through their oversight levels.

## Processes

A **process** is something a tool call started in the real world or in an app that takes a while: a ride, a delivery, a booking being confirmed. When `tool_use` calls a `long_running` function (or the result says `in_progress`), it creates a **process subscription** so progress comes back to the agent.

```ts
Subscription {               // a process subscription
  id: string                 // "sub_..."
  tool: string
  function: string
  description: string
  stages: string[]           // "driver assigned", "arriving", "dropped off"
  next_stage: number
  document_id: string | null // where progress is written
  section_id: string | null
  archived: boolean          // set after the last stage
  created_at: string
}
```

The ambient bus emits each stage as a `process_progress` input event, which starts a session like any other input, so the agent can update the document, report snags that need a question, or close things out. After the last stage the subscription archives itself. Subscriptions still running when the server restarts resume.

## The device

The **device** (`DeviceSurface`) is the phone the agent inhabits and one of its main tools. The agent writes to it through the `device` tool and the loop; a **skin** draws it. The device never reaches into memory, and memory knows nothing about the device.

```ts
DeviceState {
  island: { active: boolean, words: string }    // the dynamic island
  brief: BriefItem[]                 // the contextual brief, highest salience first
  snoozed: BriefItem[]               // cards back in the brief at their snoozed_until
  suppressions: Suppression[]        // topics the user pushed away (see salience)
  open_ux_ids: string[]              // questions on screen now
  stashed: StashedQuestion[]         // questions the user put aside, still waiting
  space_document_ids: string[]       // documents opened in Spaces
  focused_document_id: string | null // the document Spaces shows now
  focus: { [document_id]: DocumentFocus }
  discovery: { title, reason, topic_id }[]      // the Discover screen
  notifications: string[]
}
```

The **dynamic island** pulses while any session is working, with the latest status words ("Planning dinner", "Finding app"), and shrinks when nothing is happening.

The screens, as the first brief describes them:

- **Lock**: the time and date, the island, the brief and recent notifications.
- **Discover** (left): topics related to the user's interests that they did not ask for, added with `device.add_discovery`.
- **Home** (center): the island, the brief, the installed apps and tools, and the input bar (text and speech).
- **Spaces** (right): the workspace. A tab per live document, and the open document with its questions.

Two bottom sheets open over the current screen: the **card sheet**, when the user taps a brief card that has no document or that has a one-tap action, and the **question sheet** (see [Questions](#the-question-sheet)).

## The contextual brief

The **brief** is a short ranked list of glanceable **cards**: calls to action, not details. The stack of questions waiting on the user leads it, then the agent's cards ordered by salience, then a chip for stashed questions. Tapping a card opens its topic's document in Spaces, focused on the section it is about; a card with no document opens the card sheet with its detail, its topic's summary, its open questions and its action.

```ts
BriefItem {                  // a brief card
  id: string                 // "brf_..."
  text: string               // "Leave by 3pm for the dentist"
  topic_id: string | null    // a topic has at most one card
  document_id: string | null
  section_id: string | null
  ux_request_id: string | null
  urgency: string            // "urgent" | "high" | "normal" | "low"
  detail: string             // one or two sentences, for cards without a document
  action: BriefAction | null // a one-tap action
  expires_at: string | null  // the device drops the card then
  due_at: string | null      // when the thing it is about happens; drives proximity
  salience: Salience
  opened_at: string | null
  snoozed_until: string | null
  source_event_id: string | null   // the input event behind the session that wrote it
  created_at: string
  updated_at: string         // when it was written; the card is stale once its topic changes after this
}

BriefAction {                // e.g. "Call Mom"
  tool: string
  function: string
  label: string
  arguments: { [name]: string }
}
```

Tapping an action starts a session that already holds the user's approval for that one tool function (a session-scoped permission), so it is not asked about again. Any other tool in that session still asks as usual.

### Keeping the brief true

A card is a snapshot of what was true when it was written. The agent sees the current brief and the waiting questions in every step, edits single cards with `device.update_brief` (one card per topic), and gives cards an `expires_at` when they stop applying at a time. When a session changes a topic that has a card, the card becomes **stale**. At the end of the session the **brief refresh** (one model call over just the stale cards) keeps, rewrites or removes each one, and withdraws waiting questions the news answered. A sheet open on a card follows it.

### Salience

The brief is ordered by **salience** (`device/salience.py`, after Duke's salience rules):

```ts
Salience {
  urgency: number | null     // personal risk if the user does not act, 0-1 (null: use the card's urgency label)
  relevance: number          // how well it fits the user's context now, 0-1
  affinity: number           // how much the person or business involved matters, 0-1
  proximity: number          // computed: 1 when due_at is now, halving every 2 hours
  suppression: number        // computed: 0 to -1
  score: number              // computed
  scored_by: string          // "agent" or the Jev model
  scored_at: string | null
}

Suppression { key: "topic:<id>" | "text:<card text>", kind: "dismissed" | "snoozed", at: string }
```

`score = 0.4 urgency + 0.25 proximity + 0.2 relevance + 0.15 affinity + suppression`

The agent (or Jev, see below) scores urgency, relevance and affinity when it writes a card. Proximity and suppression are computed from the clock, so the order keeps moving as time passes. Suppression fades: a **dismissal** starts at -0.6 and halves every 12 hours, a **snooze** ("Not now", one hour) starts at -0.3 and halves every 6 hours, and a card left unopened for more than 2 hours loses up to 0.4 over the next 10. Suppression is kept per topic, so a new card on a topic the user dismissed also ranks lower, and returns only with real news. Cards about a document cannot be dismissed yet.

## Spaces and document focus

Spaces shows a document with only the sections that matter now expanded (at most two, unless the user opens more). The rest fold into an outline the user can open one at a time, or all at once with "Show full document".

```ts
DocumentFocus {              // a stored choice, per document
  document_id: string
  section_ids: string[]
  mode: "focused" | "full"
  reason: string             // "Your flight moved to 4pm"
  set_by: "agent" | "user" | "rule"
  updated_at: string
}

DocumentView {               // what Spaces actually shows (resolved per request)
  document_id: string
  section_ids: string[]
  mode: "focused" | "full"
  reason: string
  set_by: "agent" | "user" | "rule"
  changed_section_ids: string[]  // changed since the user last looked at the topic
}
```

Who decides, in order:

1. **The agent**, with `device.show_document(document_id, section_ids, mode, reason)`, or by answering a question (Spaces returns to the question's section).
2. **The user**, by opening sections or the full document (`POST /api/view`).
3. **A rule**, when nobody chose: sections with a waiting question, then sections changed since the user last looked, then the first open section with a suggested action.

A chosen focus holds until a section outside it changes; then the rule takes over again.

## System One decision models (Jev)

A **System One model** answers typed questions (a choice, a score, yes or no) with probabilities, fast, and writes no text. Quintessa uses **Jev** (TypeSafe AI) or **gev** (an open-source clone on Gemma) for four optional jobs. All need a Jev key; each user can switch them from the Jev menu, and their choice is saved as preferences.

| Job | Preference | What it does |
|---|---|---|
| Shadow | `jev_shadow` | At each step, asks Jev to pick the next step at the same moment as the LLM, from the same controller context and each capability's `choose_when`. The LLM still decides; Jev's pick is recorded and shown in Traces. |
| Drive | `jev_drive` (off by default) | Jev picks the next step instead of the LLM. If Jev fails, the LLM decides that step. |
| Ambient filter | `jev_filter` | Asks "does this matter?" about each ambient event before any LLM call; below the threshold (0.3) the session ends at once. User input and process progress always run. |
| Brief scoring | `jev_rank` | At the end of a session, scores urgency, relevance and affinity for new or changed cards (all cards when the user's location changed). |

```ts
ShadowDecision {             // one next-step decision by Jev
  step_index: number
  llm_choice: string         // what the LLM chose ("" when Jev drove)
  choice: string             // what Jev chose
  probabilities: { [capability or "done"]: number }
  confidence: number
  model: string
  latency_ms: number
  error: string
  drove: boolean             // Jev's choice was followed
}

PrefilterDecision {          // the ambient filter's answer
  matters: number            // P(yes)
  threshold: number
  skipped: boolean
  model: string
  latency_ms: number
  error: string              // a failed call never skips
}

Preferences {                // per user; null means "use the platform default"
  jev: boolean | null        // master switch for every System One call
  jev_shadow: boolean | null
  jev_filter: boolean | null
  jev_drive: boolean | null
  jev_rank: boolean | null
}
```

In shadow studies Jev agreed with Claude on 34-53% of next steps, at about 600 ms, and its confidence was not a reliable signal of when it was right. `python -m quintessa --user ID decisions` prints the agreement report.

## Ambient data and personas

**Ambient sources** simulate streams the user would receive: emails, texts, a drive to the office, home security, location changes. The **ambient bus** emits each source's events as input events at its own rate. Global emission is on by default with no sources. Sources come from templates (`samples/ambient_templates.json`) or are described in plain words and written by a model ("vibe coded").

```ts
AmbientSource {
  id: string                 // "src_..."
  name: string
  kind: InputEvent["kind"]
  events: string[]           // emitted in order
  interval_seconds: number   // divided by speed
  speed: number
  enabled: boolean
  loop: boolean
  device: string
  sender: string
}
```

**Aura personas** (the `posttool/persona` Cloud Functions) supply people with profiles, days and observations. Picking a persona clears the user's state, attaches the persona's profile and replays a day in their life as input events (source `persona`). The process subscriptions described above also run on the ambient bus.

## Per-user state, storage and the API

`AgentHost` keeps one agent (`AgentRuntime`) per **user id**: their memory, device, waiting questions, tools, processes, preferences and attached persona. Only the model chain and the capability files are shared.

### Agent state

The whole state of one user's agent has one portable form, used both for storage and for download and restore:

```ts
AgentStateSnapshot {
  format: "quintessa.agent-state"
  version: 1
  user_id: string
  saved_at: string
  memory: {
    nodes: MemoryNode[]; edges: MemoryEdge[]; topics: Topic[]; documents: Document[]
    tools: Tool[]; permissions: Permission[]; subscriptions: Subscription[]
    events: InputEvent[]; sessions: ReasoningSession[]
  }
  device: DeviceState
  preferences: Preferences
  persona: { profile, persona_id, date } | null
}
```

State is saved shortly after anything changes. By default it lives in SQLite at `data/quintessa.db` (`SqlStateBackend`): every table is keyed by user id, each memory item is one row, and a save writes only the rows that changed, in one transaction. `QUINTESSA_DATABASE_URL` points at another database such as Postgres (not yet tested), and `QUINTESSA_STATE=file` keeps one JSON file per user. After a restart, sessions that were mid-flight are marked `stopped` with a note in their trace, and running processes resume. A restore is fully validated before anything is replaced, and a state can be restored under another user id.

### The API

The FastAPI app (`quintessa/api/app.py`) serves the web app and a per-user HTTP API. Every call names a user with `?user=` or the `X-Quintessa-User` header. The API trusts that id; it has no authentication yet.

| Area | Endpoints |
|---|---|
| State | `GET /api/state` (everything a surface draws), `GET /api/stream` (server-sent `change` events) |
| Input | `POST /api/input` `{ kind, content, sender, device }` starts a session |
| Questions | `POST /api/ux/{id}` answers or skips one; `POST /api/ux/{id}/stash`, `/unstash` |
| Brief | `POST /api/brief/{id}/open`, `/dismiss`, `/snooze`, `/act` |
| Spaces | `POST /api/view` (the user's focus), `POST /api/topics/{id}/seen` |
| Tools and apps | `POST /api/tools`, `DELETE /api/tools/{name}`, `GET /api/apps/search`, `POST /api/apps/install`, `DELETE /api/apps/{app_id}` |
| Ambient | templates, global on/off, sources from a template or plain words, per-source speed |
| Personas | `GET /api/personas`, `POST /api/persona/start`, `/stop` |
| Settings | `PUT /api/preferences`, `GET /api/models`, `GET`/`PUT /api/settings` (model chain, retries) |
| State management | `POST /api/clear`, `GET /api/export`, `POST /api/restore` |

`GET /api/state` returns:

```ts
AgentState {
  user_id: string
  memory: AgentStateSnapshot["memory"]
  device: DeviceState
  views: { [document_id]: DocumentView }   // resolved focus for every live document
  pending_ux: UXRequest[]                  // questions waiting on the user
  ambient: { enabled: boolean, sources: (AmbientSource & { done: boolean })[] }
  persona: { profile, date, running } | null
  settings: { chain: string[], retries: number, base_delay: number, status: string }
  jev: { available, model, threshold, jev, jev_shadow, jev_filter, jev_drive, jev_rank }
  apps: { store: string }
  server_time: string
}
```

## The web app

The web app (`web/`, React and Vite) is the tool for refining the experience. It shows the **Experience** panel (the phone) beside four side panels:

- **Memory**: the graph (a force-directed layout), topics, documents, facts and permissions.
- **Tools**: installed apps with icons, functions, oversight levels and sign-in state; a store search to install or uninstall apps; agent-made and built-in tools.
- **Data**: the global on/off switch, ambient sources from templates or plain words, and per-source speed.
- **Traces**: every session grouped by its input event, each step in detail, with Jev's pick and probability per step.

The **top bar** holds the user id, the persona picker, the Jev checkbox and menu, the model chain (pulldowns of Claude and Gemini models, with retries), download and restore, clear memory, and dark or light mode.

The phone renders inside a shadow root with only its skin's stylesheet, so a **skin** is one CSS file in `web/src/experience/skins/` (`aurora` and `paper` today). Client-side state is limited to what the phone is showing at the moment: locked or not, which screen, which document tab and which sheet is open. Per-viewer conveniences (theme, user id, open panel, skin) are kept in the browser's local storage. Everything else comes from `GET /api/state`, refreshed on each `change` event.

## Not built yet

From the first brief, or found missing since:

- **Real apps and tools.** Apps, `mcp` and `code` tools are played by a model. Sign-in is never asked for.
- **Memory retrieval.** The whole memory snapshot goes into each prompt.
- **Calendar.** Key dates can be tentative ("penciled in"), but there is no calendar tool or agent-kept calendar, and no conflict spotting beyond what the model notices (`conflicts_with` edges).
- **"Why?" after a dismissal.** Dismissing a card lowers its topic for a while; the agent does not ask the user why, and the answer does not become a trigger override.
- **"Still relevant?"** for old topics with no due date, and other pruning beyond archiving.
- **Asking "what help is available?"** Suggested actions on sections, one-tap brief actions and Discover cover part of it.
- **Resuming a question across a restart.** The session is recorded as interrupted, and the next input starts fresh.
- **Authentication.** The API trusts the user id it is given.
- **Other surfaces** (a New Tab page, glasses). The API and skins are built for them, but only the phone exists.

## Glossary

One term per idea. The right-hand column lists words used for the same thing in the first brief or in older notes, which this document no longer uses.

| Term | Meaning | Replaces |
|---|---|---|
| **agent** | One user's `AgentRuntime`: their memory, device, questions, tools and processes. | |
| **input event** | Anything that starts a session: something the user said, a message, a location change, process progress. | trigger (the session's `trigger` field holds its input event), signal |
| **reasoning session** (session) | One run of the reasoning loop for one input event. | control loop, reasoning chain, chain |
| **reasoning loop** | The code that runs sessions step by step (`AgentReasoningLoop`). | primary control loop |
| **step** | One capability run inside a session, chosen by the controller. | reasoning step |
| **controller** | The model call that picks each step's capability, or `done`. | |
| **capability** | A markdown-defined kind of step: `memory`, `generative_ui`, `tool_discovery`, `tool_use`. | reasoning capability |
| **trace** | A session's recorded steps, shown in the Traces panel. | session memory, log |
| **memory** | Everything one agent knows: graph, topic index, documents, tools, permissions, processes, events, traces. | shared memory space, knowledge graph (for the whole) |
| **graph** | Memory's nodes and edges. | personal knowledge graph, KG |
| **topic** | An entry in the topic index, with trigger rules, summary, progress and due date. | card (in the first brief), wiki entry, category entry |
| **topic index** | All of a user's topics, organized by category and nesting. | index, wiki, personal wiki, graph of topics |
| **document** | The progressively built record of a topic's lifecycle, made of sections. | page, personal document, card (when growing) |
| **question** | Generated UI the session waits on (`UXRequest`), of purpose disambiguation, information or permission. | disambiguation, ux_disambiguation, form, generative UX |
| **permission prompt** | A question with purpose `permission`, asking to approve one tool function. | use gate, decision boundary |
| **permission** | A recorded answer to a permission prompt, scoped to a session or persistent. | grant |
| **tool** | A group of typed functions with oversight levels. | |
| **app** | A tool of kind `app`, installed from an app store. | |
| **oversight level** | How much user approval a function needs: `auto`, `auto_from_memory`, `confirm_once`, `always_ask`. | |
| **process** | A long-running real-world or in-app activity a tool call started. | active process (the node type keeps this name) |
| **process subscription** | The record that follows a process and emits its progress as input events. | ambient data subscription |
| **ambient source** | A simulated stream of input events (emails, texts, a drive). | ambient data stream |
| **device** | The phone surface the agent writes to (`DeviceSurface`). | device tool (that is the tool that writes to it) |
| **skin** | One stylesheet that draws the device. | design system (in the device sense) |
| **dynamic island** | The status pill at the top of the device. | |
| **brief** | The contextual brief: the ranked list of cards and waiting questions. | contextual brief, dashboard |
| **card** | One item in the brief (`BriefItem`). Not a topic. | indicator, brief item |
| **card sheet** | The bottom sheet a card opens when it has no document or has an action. | sheet |
| **question sheet** | The bottom sheet where every question is answered, as a deck. | disambiguation sheet, form |
| **stash** | Questions the user put aside; still waiting, out of the stack. | |
| **salience** | A card's ranking score. | priority |
| **Spaces** | The device screen that shows documents. | intent space, intent screen |
| **focus** | Which sections of a document Spaces expands. | |
| **Discover** | The device screen for things related to the user's interests. | discovery screen |
| **System One model** | A fast typed-decision model (Jev, gev). | |
| **persona** | An Aura persona used to replay a day in someone's life. | Aura persona tool |
| **agent state** | The portable snapshot of one agent, for storage, download and restore. | |
