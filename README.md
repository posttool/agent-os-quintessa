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
- **Durability**: each user's state is saved shortly after anything changes, through a `StateBackend`. `FileStateBackend` writes one JSON file per user, atomically. After a restart, a user's state reloads on their next request:
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
| `quintessa/state/` | state backends (file, in-memory) and the snapshot format |
| `quintessa/loop/` | `AgentReasoningLoop`, `AgentRuntime`, `UXBroker` |
| `quintessa/decide/` | System One decision models (Jev, gev) asked beside the LLM, and the agreement report |
| `quintessa/tools/` | built-in `web` and `device` tools and the tool runner |
| `quintessa/device/` | device surface state |
| `quintessa/ambient/` | ambient data bus and template-based generators |
| `quintessa/persona/` | Aura persona client and day-in-the-life simulation |
| `quintessa/samples/` | bootstrap data: tool suggestions, ambient templates |
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

Web search uses Gemini's Google Search grounding when `GOOGLE_CLOUD_PROJECT` is set.

### Jev shadow mode

[Jev](https://docs.typesafe.ai/) is a decision model: it answers typed questions with probabilities and writes no text. With a key set, every next-step decision is also put to Jev as a Choice over the capabilities and "done", at the same moment as the LLM. The LLM still decides; Jev's pick, probabilities, confidence and latency are kept on the session (`shadow_decisions`) and shown under each step in the Traces panel.

- `QUINTESSA_JEV_API_KEY` turns it on (`TYPESAFE_API_KEY` also works). `QUINTESSA_DECIDER=llm` turns it off.
- `QUINTESSA_JEV_URL` points it at another endpoint with the same `/v1/systemone` API, such as [gev](https://github.com/dglazkov/gev), the open-source one on Gemma. `QUINTESSA_JEV_MODEL` defaults to `jev-latest`.
- Each capability's `choose_when` front matter is the criterion Jev reads for it.
- `python -m quintessa --user ID decisions` prints how often Jev agreed with the LLM, per choice and by confidence.

**Ambient filter.** With `QUINTESSA_AMBIENT_FILTER=1` (and a Jev key), each ambient event and persona replay is first put to Jev as one yes/no question, "does this matter?", along with an outline of what the agent is tracking. Below `QUINTESSA_AMBIENT_THRESHOLD` (default 0.3) the session ends with no LLM call and shows as skipped in Traces. What the user says, process progress and the persona profile always run, and a failed Jev call never skips anything. On 60 hand-labeled events (`/mnt/project-files/jev-eval/ambient_events.csv` in the project) it skipped half of them and missed none that mattered, at about 0.6 s a check against about 6 s for the controller's first decision.

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

Questions the agent asks are answered in the terminal. Agent state lives in `data/agents/`, one file per user.

## Web app

```bash
cd web && npm install && npm run build && cd ..
uv run python -m quintessa serve     # http://127.0.0.1:8000
```

For UI work, run `uv run python -m quintessa serve` and `cd web && npm run dev` side by side. Vite proxies `/api` to port 8000.

- **User**: every API call names a user with `?user=` or the `X-Quintessa-User` header. The top bar sets it, so two browser tabs with different users have separate agents.
- **Experience**: a phone with Lock, Discover, Home and Spaces screens, the dynamic island, the contextual brief and an input bar (text and speech). Open questions from the agent appear first in the brief. Spaces opens a document showing only the sections that matter now (chosen by the agent's `device.show_document`, or by a rule: sections with a waiting question, then sections changed since the user last looked, then the first open section with a next step). The rest fold into an outline the user can open one at a time, or all at once with "Show full document"; `POST /api/view` records the user's choice, which holds until another part of the document changes. The phone renders inside a shadow root with only its skin's stylesheet, so a skin is one CSS file in `web/src/experience/skins/` (`aurora` and `paper` so far).
- **Memory**: the graph, topics, documents, facts and permissions.
- **Tools**: built-in and agent-made tools; create or delete your own.
- **Data**: the global on/off switch (on, with no sources), sources from templates or described in plain words ("vibe coded"), and per-source speed.
- **Traces**: every reasoning step, grouped by the input that started it.
- **Top bar**: Aura persona picker (clears the user's state and plays a day), model chain with retries and fallbacks, download and restore of agent state, clear memory, dark and light mode.

The app starts blank. With no model configured, inputs fail with a message saying so; set the chain in the top bar or with `QUINTESSA_MODEL_CHAIN`.

## Not yet built

- Executing `web_api`, `mcp` and `code` tools. They can be defined and stored, but calls report that they are not implemented yet.
- Memory retrieval: the whole graph currently goes into each prompt.
- Resuming a question that was open during a restart: the session is recorded as interrupted, and the next input starts fresh.
- Authentication: the API trusts the user id it is given. It must check identity before it is exposed beyond localhost.
