# Agent OS: Quintessa

A personal agent operating system. An LLM-driven reasoning loop works over a shared memory graph of the user's world, and a device surface shows what matters right now.

Built from the [spec](docs/spec.md) in two phases: the Python backend with its data structures and tests, and a web app with a phone Experience panel plus Memory, Tools, Data and Traces panels.

## How it works

```
request (user_id, input: text, speech, message, location, vision, process progress)
   │
   ▼
AgentHost ──► that user's AgentRuntime (loaded from storage on first use)
   │
   ▼
AgentRuntime.submit(event) ──► AgentReasoningLoop (one per input, many at once)
                                  │  each step the model picks ONE capability, or "done"
                                  ├─ memory          read, write and organize the graph, topics and documents
                                  ├─ generative_ui   ask the user; the loop pauses until they answer
                                  ├─ tool_discovery  find or define typed tools
                                  └─ tool_use        call one tool function (web, device, or agent-made tools)
                                  │
                                  ▼
                 MemoryStore (shared)        DeviceSurface (island, brief, Spaces, Discover)
```

- **Capabilities are markdown files** in `quintessa/capabilities/`. Each file's front matter names its executor. The set is configurable: `load_capabilities(dir, names=[...])`. The controller prompt is `_controller.md`.
- **The LLM does the reasoning.** Every model call returns JSON that matches a closed schema (Claude structured outputs, Gemini `response_json_schema`). Our code only applies those structured decisions; it never parses text to decide anything.
- **Memory** is a graph with typed nodes (preference, project context, ambient state, tool knowledge, active process, document, person, routine) and typed edges. It also holds an index of topics, documents with a lifecycle, tools, permissions and process subscriptions. Raw events are kept for audit only. User-set trigger rules survive agent updates.
- **Disambiguation** pauses the loop on a `UXRequest`. The answer comes back to the context that asked (a document section or a pending tool call), and the device closes the form and returns to that section.
- **Oversight**: each tool function has a level (`auto`, `auto_from_memory`, `confirm_once`, `always_ask`).
  - A grant given anywhere in a chain carries forward to later steps in that chain.
  - `confirm_once` grants are kept in memory for later sessions.
- **Long-running tool calls** create a `Subscription`. The ambient bus then emits progress events back into the loop and archives the subscription when the process completes.
- **Resilience**: `ResilientLLM` retries transient errors and bad output with backoff, then falls back along the model chain. A session that runs out of models is marked failed, with the error in its trace, and the other loops keep running.
- **Per-user state**: there is no global memory. Every `AgentHost` call takes a `user_id`, and each user has their own memory, device surface, pending questions, tools and process subscriptions. Only the model chain and the capability definitions are shared.
- **Durability**: each user's state is saved shortly after anything changes, through a `StateBackend`. `SqlStateBackend` keeps it in a database: every table is keyed by user id, each memory item is one row (its JSON plus a few indexed columns), and a save writes only the rows that changed, in one transaction. The Aura persona a user attached is saved too. After a restart, a user's state reloads on their next request:
  - Process subscriptions that were still running resume.
  - Sessions that were mid-flight are marked stopped, and their trace notes that a restart interrupted them.
- **Download and restore**: `host.export_state(user_id)` returns the whole agent state as one versioned JSON document. `host.restore_state(user_id, data)` replaces a user's state with one. A restore is fully validated before anything is replaced, and a state can be restored under a different user id.
- **Separation**: memory and reasoning know nothing about any design system. Surfaces subscribe to `MemoryStore.listen` and `DeviceSurface.listen`.

## Layout

| Path | What |
|---|---|
| `quintessa/models/` | dataclasses and enums, one per file |
| `quintessa/llm/` | `ClaudeAdapter`, `GeminiVertexAdapter`, `ResilientLLM`, schema helpers, `ScriptedLLM` for tests |
| `quintessa/capabilities/` | capability markdown and loader |
| `quintessa/executors/` | code that applies each capability's output |
| `quintessa/memory/` | `MemoryStore` and memory operations |
| `quintessa/host.py` | `AgentHost`: per-user agents, saving, download and restore |
| `quintessa/state/` | state backends (SQL, file, in-memory) and the snapshot format |
| `quintessa/loop/` | `AgentReasoningLoop`, `AgentRuntime`, `UXBroker` |
| `quintessa/decide/` | System One decision models (Jev, gev) asked beside the LLM, and the agreement report |
| `quintessa/tools/` | built-in `web` and `device` tools and the tool runner |
| `quintessa/apps/` | app stores (Play, web search, bundled catalog) and installing apps as tools |
| `quintessa/device/` | device surface state |
| `quintessa/ambient/` | ambient data bus and template-based generators |
| `quintessa/persona/` | Aura persona client and day-in-the-life simulation |
| `quintessa/samples/` | bootstrap data: tool suggestions, ambient templates, the offline app catalog |
| `quintessa/api/` | FastAPI app: per-user HTTP API, live change stream, serves the web app |
| `web/` | React web app (Vite, TypeScript) |

## Setup

```bash
uv venv && uv pip install -e ".[dev]"
uv run pytest
```

`uv run` uses the project's `.venv`, so nothing needs activating. Without uv, use `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`, then drop the `uv run` prefix from the commands below. Running them with a Python outside that virtualenv gives errors such as `ModuleNotFoundError: No module named 'httpx'`.

### Models

The model chain is a list of `provider:model` pairs, tried in order:

```bash
export QUINTESSA_MODEL_CHAIN="gemini:gemini-3.8-flash,gemini:gemini-2.5-flash"   # default
export QUINTESSA_MODEL_CHAIN="claude:claude-opus-5-5,claude:claude-opus-5,gemini:gemini-3.8-flash"
```

- **Gemini on Vertex**: run `gcloud auth application-default login`, then set `GOOGLE_CLOUD_PROJECT` (and optionally `GOOGLE_CLOUD_LOCATION`, default `global`).
  - Where secrets can only be environment variables (such as a hosted environment), put a service account key's whole JSON in `QUINTESSA_GCP_SA_JSON` instead. The account needs the Vertex AI User role. `GOOGLE_CLOUD_PROJECT` then defaults to the key's project.
- **Claude**: set `QUINTESSA_ANTHROPIC_API_KEY`, or `ANTHROPIC_API_KEY` if that is not set. The Quintessa name is there because some hosts, such as Claude Code cloud sessions, keep `ANTHROPIC_API_KEY` for themselves. To route Claude through Vertex instead, set `QUINTESSA_CLAUDE_ON_VERTEX=1` with the Google variables above. On the Anthropic API, current models also get Anthropic's server-side refusal fallback.
- `QUINTESSA_LLM_RETRIES` sets retries per model (default 2).

Web search uses Gemini's Google Search grounding when `GOOGLE_CLOUD_PROJECT` is set, and otherwise Claude's web search tool when an Anthropic key is set (`QUINTESSA_SEARCH_MODEL` picks the model, default `claude-opus-5-5`).

Tools the agent discovers run by kind: `web_api` tools make a real HTTP request (the model writes the request from the tool's endpoint), while `llm`, `mcp` and `code` tools are played by a model grounded in the tool's description, since MCP and agent-written code have no runtime yet. A network error fails that one call rather than the whole session.

### Apps

When the user wants something done that people do in a phone app (book a table, order food, get a ride), `tool_discovery` searches an app store, picks an app (one the user is known to use first) and installs it. A model writes the app's functions and oversight levels from its store listing. An installed app is a `Tool` of kind `app` in that user's memory, so it is saved, exported and restored like everything else, and only installed tools can be called.

Each app records its store `listing` (id, title, developer, icon), its `binding` (how calls run) and its `auth` (what sign-in it would need). Every app is `simulated` for now: a model grounded in the listing plays the app, and sign-in is skipped. Each simulated call runs into a realistic problem (sold out, no driver, payment declined) about one time in five; the outcome is drawn in code and `QUINTESSA_SIM_FAILURE_RATE` changes it (default `0.2`). The binding values `mcp`, `web_api` and `android` are reserved for real backends, and the runner already returns "sign in first" for an app whose auth state is `needed`.

`QUINTESSA_APP_STORE` picks the store:

- `play`: Google Play through the `google-play-scraper` library, with real icons. Needs access to play.google.com.
- `search`: web search limited to Play listings, with no icons.
- `offline`: a bundled catalog of 44 common apps, with no icons.
- `auto` (the default): Play, then web search, then the catalog. A store that fails is skipped.

The agent installs apps without asking, and never asks which app or service to use: it picks one (an app memory says the user uses, otherwise the best-known one). Installing never grants an app's risky functions; those still go through their oversight levels.

### Jev shadow mode

[Jev](https://docs.typesafe.ai/) is a decision model: it answers typed questions with probabilities and writes no text. With a key set, every next-step decision is also put to Jev as a Choice over the capabilities and "done", at the same moment as the LLM. The LLM still decides; Jev's pick, probabilities, confidence and latency are kept on the session (`shadow_decisions`) and shown under each step in the Traces panel. Each step's header carries a `Jev p` badge: the probability Jev gave the step the LLM chose, green when Jev's own top pick agrees.

- `QUINTESSA_JEV_API_KEY` turns it on (`TYPESAFE_API_KEY` also works). `QUINTESSA_DECIDER=llm` turns it off.
- `QUINTESSA_JEV_URL` points it at another endpoint with the same `/v1/systemone` API, such as [gev](https://github.com/dglazkov/gev), the open-source one on Gemma. `QUINTESSA_JEV_MODEL` defaults to `jev-latest`.
- Each capability's `choose_when` front matter is the criterion Jev reads for it.
- `python -m quintessa --user ID decisions` prints how often Jev agreed with the LLM, per choice and by confidence.

**Ambient filter.** With `QUINTESSA_AMBIENT_FILTER=1` (and a Jev key), each ambient event and persona replay is first put to Jev as one yes/no question, "does this matter?", along with an outline of what the agent is tracking. Below `QUINTESSA_AMBIENT_THRESHOLD` (default 0.3) the session ends with no LLM call and shows as skipped in Traces. What the user says, process progress and the persona profile always run, and a failed Jev call never skips anything. On 60 hand-labeled events (`/mnt/project-files/jev-eval/ambient_events.csv` in the project) it skipped half of them and missed none that mattered, at about 0.6 s a check against about 6 s for the controller's first decision.

**Turning Jev on and off.** Each user can switch Jev off entirely, or just the shadow or the filter, from the Jev checkbox and its ▾ menu in the top bar (`PUT /api/preferences`). The choice is saved with the user's state and survives Clear memory. With a key set, both are available to every user; `QUINTESSA_DECIDER=llm` and `QUINTESSA_AMBIENT_FILTER=1` only set what users start with, and Reset returns to those defaults.

**Letting Jev drive.** The third box in that menu, off by default, lets Jev pick each next step instead of the LLM: the controller's decide call is skipped and the step shows "chosen by Jev" with its probability in Traces. The capability still runs on the LLM, with no focus from the controller. If Jev fails, the LLM decides that step as usual. In the shadow studies Jev agreed with Claude on only 34-53% of next steps, so expect different behavior. Driven choices are left out of the agreement report.

### Aura personas

`AuraPersonaClient` reads personas, days and observations from the [persona](https://github.com/posttool/persona) Cloud Functions, using the Firebase callable protocol. Set `AURA_PERSONA_BASE_URL` if the functions are not at `https://us-central1-aura-persona.cloudfunctions.net`. For the local emulator, use `http://localhost:5001/aura-persona/us-central1`.

### Try it

```bash
uv run python -m quintessa --user maya say "Jane wants to do dinner at Zuni on Tuesday"
uv run python -m quintessa personas
uv run python -m quintessa --user maya persona <persona-id> --speed 600
uv run python -m quintessa --user maya export maya-agent.json     # download
uv run python -m quintessa --user maya restore maya-agent.json    # restore
uv run python -m quintessa --user maya clear
uv run python -m quintessa users
```

Questions the agent asks are answered in the terminal.

### Where state is kept

Agent state lives in a SQLite database, `data/quintessa.db`; `--data` moves the whole folder. There is no database server to install. Files the agent downloads go in `data/downloads/`, in a folder per user.

- `QUINTESSA_DATABASE_URL` points at another database, such as `postgresql://user:pass@host/quintessa` (install the driver with `uv pip install -e ".[postgres]"`). The schema is created and upgraded on first use.
- `QUINTESSA_STATE=file` goes back to the old store, one JSON file per user in `data/agents/`.
- State saved by earlier versions in `data/agents/` is imported on first start, and each file is renamed to `.json.imported`. To go back, rename them and set `QUINTESSA_STATE=file`.
- Run one server per database.

## Web app

```bash
cd web && npm install && npm run build && cd ..
uv run python -m quintessa serve     # http://127.0.0.1:8000
```

For UI work, run `uv run python -m quintessa serve` and `cd web && npm run dev` side by side. Vite proxies `/api` to port 8000.

- **User**: every API call names a user with `?user=` or the `X-Quintessa-User` header. The top bar sets it, so two browser tabs with different users have separate agents.
- **Experience**: a phone with Lock, Discover, Home and Spaces screens, the dynamic island, the contextual brief and an input bar (text and speech). Open questions from the agent appear first in the brief. The brief stays current: the agent sees it (and which cards are stale) in every step, edits single cards with `device.update_brief`, keeps one card per topic, and drops a card at its `expires_at`. When a session changes a topic that has a card, one model call at the end of the session keeps, rewrites or removes that card, and withdraws waiting questions the news answered. Cards are ranked by salience (`quintessa/device/salience.py`): urgency, how soon `due_at` is, fit with the user's context now, affinity for the person or business involved, minus a fading penalty for topics the user dismissed, snoozed ("Not now") or left unopened. The agent scores each card; with Jev ranking on (per-user `jev_rank`, on by default when a Jev key is set) Jev scores urgency, context fit and affinity with three score questions instead, for new or changed cards and for every card when the user's location changes. Spaces opens a document showing only the sections that matter now (chosen by the agent's `device.show_document`, or by a rule: sections with a waiting question, then sections changed since the user last looked, then the first open section with a next step). The rest fold into an outline the user can open one at a time, or all at once with "Show full document"; `POST /api/view` records the user's choice, which holds until another part of the document changes. The phone renders inside a shadow root with only its skin's stylesheet, so a skin is one CSS file in `web/src/experience/skins/` (`aurora` and `paper` so far).
- **Memory**: the graph, topics, documents, facts and permissions.
- **Tools**: installed apps with their icons, functions and sign-in state, a store search to install or uninstall apps yourself and the other built-in and agent-made tools.
- **Data**: the global on/off switch (on, with no sources), sources from templates or described in plain words ("vibe coded"), and per-source speed.
- **Traces**: every reasoning step, grouped by the input that started it. App searches show the candidates, with a check on the ones installed.
- **Top bar**: Aura persona picker (clears the user's state and plays a day), Jev on/off, model chain (pulldowns of Claude and Gemini models, or any `provider:model`) with retries and fallbacks, download and restore of agent state, clear memory, dark and light mode.

The app starts blank. With no model configured, inputs fail with a message saying so; set the chain in the top bar or with `QUINTESSA_MODEL_CHAIN`.

## Not yet built

- Running `mcp` and `code` tools and real apps. A model plays them for now.
- Memory retrieval: the whole graph currently goes into each prompt.
- Resuming a question that was open during a restart: the session is recorded as interrupted, and the next input starts fresh.
- Authentication: the API trusts the user id it is given. It must check identity before it is exposed beyond localhost.
