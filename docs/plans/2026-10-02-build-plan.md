# Quintessa Agent OS: proposed build plan

> **Date:** 2026-10-02  
> **Status:** Built. Duke answered the open questions on 2026-10-02 (repo posttool/agent-os-quintessa, Aura is posttool/persona, Claude and Gemini on Vertex). Phase 1 landed as the first commit on main (4fbac65), per-user state in [PR #1](https://github.com/posttool/agent-os-quintessa/pull/1), and Phase 2 in [PR #2](https://github.com/posttool/agent-os-quintessa/pull/2).  
> **Source:** `spec/build-plan.md` in the project files, copied as written. The spec it refers to is [docs/spec.md](../spec.md).

Source spec: [quintessa-agent-os-spec.md](../spec.md) (copied from Duke's gist, 2026-10-02).
Status: draft, nothing built yet. Waiting on Duke for a repo and the open questions below.

## Phase 1: core backend (Python), data structures and tests first

The spec says to build these before any UI.

- `AgentReasoningLoop`: picks one capability per step, or decides the chain is done. Any input starts a session (text, speech, message, location, camera event). Several loops run at once against shared memory. LLM calls retry, then fall back to older models.
- Capabilities are configurable markdown files: `memory.md`, `tool_discovery.md`, `tool_use.md`, `generative_ui.md` (the disambiguation UI).
- No regex or string parsing for reasoning. The LLM decides, using structured (JSON schema) output.
- One dataclass per file. For example: `Event`, `Session`, `TraceStep`, `MemoryNode`, `MemoryEdge`, `Topic`, `Document`, `DocumentSection`, `TriggerSpec`, `Tool`, `ToolFunction`, `OversightLevel`, `Permission`, `UXRequest`, `UXResponse`, `AmbientSource`, `Subscription`.
- Memory graph:
  - Node types: personal preference, project context, ambient state, tool knowledge, active process, document.
  - Edge types: relates_to, executing_for, and so on.
  - The LLM merges new information and prunes stale nodes. Raw events are kept only for audit.
- Topic index metadata: trigger types (time, location, activity, observation), user overrides, summary and "new since last seen", progress, due dates.
- Documents: progressive, nested records with a lifecycle. They hold sections, actions, links, key dates and observations, and are archived once complete.
- Disambiguation: the loop pauses on a `UXRequest`. It resumes with the form values and the originating context. A permission the user grants carries forward through the chain and is saved to memory.
- Tools: a tool is a set of typed function signatures, each with an oversight level (from "auto-fill from memory" to "always ask"). The only built-in tools are web access and device control. Long-running tool calls subscribe to an ambient progress stream.
- Sample bootstrap data (tool and ambient-source suggestions) lives in separate files. Persona material comes from "Aura".
- Memory and reasoning stay cleanly separate from any design system, so they can be reached from any device (API-first).

## Phase 2: web app

- Main Experience panel: a phone frame, an isolated stylesheet that can be swapped as a skin, a dynamic island, a contextual brief, and the Lock, Discover, Home and Spaces screens.
- Side panels:
  - Memory: the graph view.
  - Tools: create, manage and delete tools.
  - Data: ambient sources, templates, per-source speed, a global on/off switch.
  - Traces: every reasoning step, indexed by trigger.
- Controls: clear memory, dark/light mode, Gemini model picker (3.8 Flash by default) with the retry and fallback strategy, and a persona picker that starts a "day in the life" simulation.
- Start from a blank slate, with no sample data.

## Open questions for Duke

1. Where should the code live? This project has no repo yet.
2. What is the "Aura persona tool"? Is it an API, a package or a dataset, and how do we reach it?
3. What is the Gemini access path (API key, Vertex)? Which models count as the "older" fallbacks?
4. Can we get "Nadav's drawing"? The spec references it.
5. Which stacks to use? Default: FastAPI, asyncio, pydantic and dataclasses, and pytest for the backend; React and Vite for the web app.
