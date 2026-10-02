# Agent OS: Quintessa

A personal agent operating system. An LLM-driven reasoning loop works over a shared memory graph of the user's world, and a device surface shows what matters right now.

This is phase 1 of the [spec](docs/spec.md): the Python backend, its data structures and tests. Phase 2 is the web app (an Experience panel plus Memory, Tools, Data and Traces panels).

## How it works

```
input (text, speech, message, location, vision, process progress)
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
- **Separation**: memory and reasoning know nothing about any design system. Surfaces subscribe to `MemoryStore.listen` and `DeviceSurface.listen`.

## Layout

| Path | What |
|---|---|
| `quintessa/models/` | dataclasses and enums, one per file |
| `quintessa/llm/` | `ClaudeAdapter`, `GeminiVertexAdapter`, `ResilientLLM`, schema helpers, `ScriptedLLM` for tests |
| `quintessa/capabilities/` | capability markdown and loader |
| `quintessa/executors/` | code that applies each capability's output |
| `quintessa/memory/` | `MemoryStore` and memory operations |
| `quintessa/loop/` | `AgentReasoningLoop`, `AgentRuntime`, `UXBroker` |
| `quintessa/tools/` | built-in `web` and `device` tools and the tool runner |
| `quintessa/device/` | device surface state |
| `quintessa/ambient/` | ambient data bus and template-based generators |
| `quintessa/persona/` | Aura persona client and day-in-the-life simulation |
| `quintessa/samples/` | bootstrap data: tool suggestions, ambient templates |

## Setup

```bash
uv venv && uv pip install -e ".[dev]"
pytest
```

### Models

The model chain is a list of `provider:model` pairs, tried in order:

```bash
export QUINTESSA_MODEL_CHAIN="gemini:gemini-3.8-flash,gemini:gemini-2.5-flash"   # default
export QUINTESSA_MODEL_CHAIN="claude:claude-opus-5-5,claude:claude-opus-5,gemini:gemini-3.8-flash"
```

- **Gemini on Vertex**: run `gcloud auth application-default login`, then set `GOOGLE_CLOUD_PROJECT` (and optionally `GOOGLE_CLOUD_LOCATION`, default `global`).
- **Claude**: set `ANTHROPIC_API_KEY`. To route Claude through Vertex instead, set `QUINTESSA_CLAUDE_ON_VERTEX=1` with the Google variables above. On the Anthropic API, current models also get Anthropic's server-side refusal fallback.
- `QUINTESSA_LLM_RETRIES` sets retries per model (default 2).

Web search uses Gemini's Google Search grounding when `GOOGLE_CLOUD_PROJECT` is set.

### Aura personas

`AuraPersonaClient` reads personas, days and observations from the [persona](https://github.com/posttool/persona) Cloud Functions, using the Firebase callable protocol. Set `AURA_PERSONA_BASE_URL` if the functions are not at `https://us-central1-aura-persona.cloudfunctions.net`. For the local emulator, use `http://localhost:5001/aura-persona/us-central1`.

### Try it

```bash
python -m quintessa say "Jane wants to do dinner at Zuni on Tuesday"
python -m quintessa personas
python -m quintessa persona <persona-id> --speed 600
```

Questions the agent asks are answered in the terminal. Memory is saved to `data/memory.json`; pass `--fresh` to start empty.

## Not yet built

- The phase 2 web app.
- Executing `web_api`, `mcp` and `code` tools. They can be defined and stored, but calls report that they are not implemented yet.
- Memory retrieval: the whole graph currently goes into each prompt.
