# Agent OS: Quintessa

A personal agent operating system. An LLM-driven reasoning loop works over each user's memory of their world, and a device surface (a phone, in the web app) shows what matters right now.

- **[docs/overview.md](docs/overview.md)** describes the whole system as it is today, with its schemas and a glossary. This README uses its vocabulary.
- **[docs/README.md](docs/README.md)** indexes the original brief ([docs/spec.md](docs/spec.md)) and every plan written so far.

## Quick start

```bash
uv sync --extra dev                                   # Python 3.11+, installs into .venv
uv run pytest                                         # the tests use a scripted model, no keys needed
cd web && npm install && npm run build && cd ..       # the web app
export QUINTESSA_ANTHROPIC_API_KEY=...                # or set up Gemini on Vertex, see Models
export QUINTESSA_MODEL_CHAIN="claude:claude-opus-5-5,claude:claude-sonnet-5-5"
uv run python -m quintessa serve                      # http://127.0.0.1:8000
```

`uv run` uses the project's `.venv`, so nothing needs activating. Without uv, use `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"` and drop the `uv run` prefix. Running with a Python outside that virtualenv gives errors such as `ModuleNotFoundError: No module named 'httpx'`.

After pulling new changes, run `uv sync --extra dev` and `npm install && npm run build` in `web/` again, then restart the server.

### Before you push

```bash
uv run ruff check quintessa tests            # lint (rules and line length in pyproject.toml)
uv run ruff format quintessa tests           # format
uv run pytest -q
cd web && npm run build                      # type-checks the web app too
```

GitHub Actions runs the same checks on every pull request (`.github/workflows/ci.yml`).

## How it works

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
```

- **The LLM does the reasoning.** Every model call returns JSON that matches a closed schema (Claude structured outputs, Gemini `response_json_schema`). Code only carries out those structured decisions; it never parses text to decide anything.
- **Capabilities are markdown files** in `quintessa/capabilities/`. Each file's front matter names its executor and says when to choose it; the body is the capability's prompt. The controller's prompt is `_controller.md`. `load_capabilities(dir, names=[...])` picks the set.
- **Prompts are files too.** Every other fixed text sent to a model is a markdown file in `quintessa/prompts/` (front matter says where it is used and which `{placeholders}` it takes), Jev's questions are YAML in `quintessa/prompts/jev/`, and the built-in tools are defined in `quintessa/tools/builtin_tools.yaml`. Tuning the agent's wording never means editing Python.
- **One context for every model.** What the controller, each capability and Jev read is assembled in `quintessa/context.py`, so the LLM and Jev decide from the same facts.
- **Memory** holds a graph of typed nodes and edges, the topic index, documents (each the growing record of one topic, made of sections), tools, permissions, process subscriptions, raw input events (for audit only) and the trace of every session.
- **Questions.** A `generative_ui` step, or a tool call that needs approval, asks the user a question and the session waits. Every question is answered in the question sheet; waiting questions stack at the top of the brief, and the user can stash one for later. The answer returns to the context that asked (a document section, a pending tool call).
- **Oversight.** Each tool function has an oversight level: `auto`, `auto_from_memory`, `confirm_once` (the answer is kept in memory) or `always_ask`. A permission given in a session carries through the rest of that session. The rules are in `quintessa/oversight.py`.
- **Apps.** When the user wants something done that people do in a phone app, `tool_discovery` searches an app store, picks an app and installs it without asking. Installed apps are played by a model for now. See [Apps](#apps).
- **Processes.** A long-running tool call (a ride, a delivery) creates a process subscription, which sends progress back in as input events and archives itself when the process completes.
- **The brief** is a ranked list of cards. The agent edits single cards, keeps one card per topic, and drops a card at its `expires_at`. After a session that changed a topic with a card, one model call keeps, rewrites or removes that card and withdraws questions the news answered. Cards are ordered by salience (`quintessa/device/salience.py`).
- **Spaces** shows a document with only the sections that matter now expanded; the rest fold into an outline.
- **System One models.** With a Jev key, a fast typed-decision model is asked beside the LLM: it shadows next-step choices, can skip ambient events that don't matter, and can score cards. See [Jev](#jev).
- **Resilience.** `ResilientLLM` retries transient errors and bad output with backoff, then falls back along the model chain. A session that runs out of models is marked failed with the error in its trace; other sessions keep running.
- **Per-user, durable state.** There is no global memory. Every `AgentHost` call takes a `user_id`; each user has their own memory, device, questions, tools and processes. Only the model chain and the capability definitions are shared. State is saved shortly after any change, reloads on the user's next request after a restart (running process subscriptions resume; sessions that were mid-flight are marked interrupted), and can be downloaded and restored as one versioned JSON document (version 2; version 1 files are upgraded as they load).
- **Separation.** Memory and reasoning know nothing about any skin. Surfaces subscribe to `MemoryStore.listen` and `DeviceSurface.listen`.

## Layout

| Path | What |
|---|---|
| `quintessa/models/` | dataclasses and enums, one per file (`Question`, `Answer`, `Topic`, `Document`, `Tool`, ...) |
| `quintessa/capabilities/` | capability markdown files, the controller prompt, and the loader |
| `quintessa/prompts/` | every other prompt, as markdown; Jev's questions as YAML in `jev/` |
| `quintessa/loop/` | `AgentRuntime` (one user's agent), `AgentReasoningLoop`, `QuestionBroker` (waiting questions), and the end-of-session brief refresh |
| `quintessa/context.py` | what the models read: controller, capability and brief context, card staleness |
| `quintessa/executors/` | the code that carries out each capability's output |
| `quintessa/oversight.py` | whether a tool call may run now, and what an approval leaves behind |
| `quintessa/memory/` | `MemoryStore` and the memory operations |
| `quintessa/device/` | `DeviceSurface` and its state: cards (`Card`, built in `cards.py`) and salience, document focus, stash |
| `quintessa/tools/` | the built-in `web` and `device` tools (defined in `builtin_tools.yaml`), the tool runner, web search backends |
| `quintessa/apps/` | app stores (Play, web search, bundled catalog) and installing apps as tools |
| `quintessa/decide/` | System One models (Jev, gev): next step, ambient filter, card scoring, `JevSwitches`, agreement report |
| `quintessa/llm/` | `ClaudeAdapter`, `GeminiVertexAdapter`, `ResilientLLM`, schema helpers, the model picker's catalog, `ScriptedLLM` for tests |
| `quintessa/host.py` | `AgentHost`: per-user agents, saving, download and restore, the shared model chain |
| `quintessa/state/` | state backends (SQL, file, in-memory) and the agent state format |
| `quintessa/config.py` | every environment variable, read in one place |
| `quintessa/ambient/` | ambient sources and their generators |
| `quintessa/persona/` | Aura persona client and day replay |
| `quintessa/samples/` | bootstrap data: tool suggestions, ambient templates, the offline app catalog, the model picker's list |
| `quintessa/api/` | FastAPI app (`app.py`) with one router per area in `routes/`: per-user HTTP API, live change stream, serves the web app |
| `quintessa/cli.py` | the command line (`python -m quintessa`) |
| `web/` | React web app (Vite, TypeScript) |
| `tests/` | pytest suite |
| `docs/` | overview, original brief, plans |

## Configuration

### Models

The model chain is a list of `provider:model` pairs, tried in order. It can also be changed at runtime from the web app's top bar.

```bash
export QUINTESSA_MODEL_CHAIN="gemini:gemini-3.8-flash,gemini:gemini-2.5-flash"   # default
export QUINTESSA_MODEL_CHAIN="claude:claude-opus-5-5,claude:claude-opus-5,gemini:gemini-3.8-flash"
```

- **Claude**: set `QUINTESSA_ANTHROPIC_API_KEY`, or `ANTHROPIC_API_KEY` if that is not set. The Quintessa name exists because some hosts, such as Claude Code cloud sessions, keep `ANTHROPIC_API_KEY` for themselves. On the Anthropic API, current models also get Anthropic's server-side refusal fallback. To route Claude through Vertex instead, set `QUINTESSA_CLAUDE_ON_VERTEX=1` with the Google variables below.
- **Gemini on Vertex**: run `gcloud auth application-default login`, then set `GOOGLE_CLOUD_PROJECT` (and optionally `GOOGLE_CLOUD_LOCATION`, default `global`). Where secrets can only be environment variables, put a service account key's whole JSON in `QUINTESSA_GCP_SA_JSON` instead. The account needs the Vertex AI User role, and `GOOGLE_CLOUD_PROJECT` then defaults to the key's project.

With no model configured the server still starts, and every input fails with a message saying what is missing.

### Environment variables

All of these are read through `quintessa/config.py`.

| Variable | Default | What it does |
|---|---|---|
| `QUINTESSA_MODEL_CHAIN` | `gemini:gemini-3.8-flash,gemini:gemini-2.5-flash` | model chain, tried in order |
| `QUINTESSA_LLM_RETRIES` | `2` | retries per model before falling back |
| `QUINTESSA_ANTHROPIC_API_KEY` | | Anthropic key (`ANTHROPIC_API_KEY` is the fallback) |
| `QUINTESSA_CLAUDE_ON_VERTEX` | | `1` sends Claude through Vertex |
| `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` | `global` location | Vertex project and location |
| `QUINTESSA_GCP_SA_JSON` | | a service account key's JSON, when no credentials file is set |
| `QUINTESSA_SEARCH_MODEL` | `claude-opus-5-5` | model for Claude web search |
| `QUINTESSA_APP_STORE` | `auto` | `play`, `search`, `offline` or `auto` (see [Apps](#apps)) |
| `QUINTESSA_SIM_FAILURE_RATE` | `0.2` | how often a simulated app call runs into a problem |
| `QUINTESSA_PICTURE_SEARCH` | `wikimedia` | where real pictures for tool results come from; `off` draws them instead |
| `QUINTESSA_JEV_API_KEY` | | turns on Jev (`TYPESAFE_API_KEY` also works) |
| `QUINTESSA_JEV_URL`, `QUINTESSA_JEV_MODEL` | TypeSafe's API, `jev-latest` | another `/v1/systemone` endpoint, such as gev |
| `QUINTESSA_DECIDER` | `shadow` | `llm` starts users with the Jev shadow off |
| `QUINTESSA_AMBIENT_FILTER`, `QUINTESSA_AMBIENT_THRESHOLD` | off, `0.3` | `1` starts users with the ambient filter on |
| `QUINTESSA_DATABASE_URL` | SQLite at `data/quintessa.db` | where agent state is kept |
| `QUINTESSA_STATE` | | `file` uses one JSON file per user instead of the database |
| `AURA_PERSONA_BASE_URL` | the aura-persona Cloud Functions | Aura persona service |
| `QUINTESSA_USER` | `local` | the CLI's default `--user` |
| `QUINTESSA_WEB_DIST` | `web/dist` | the built web app the server serves |

### Web search and tools

Web search uses Gemini's Google Search grounding when `GOOGLE_CLOUD_PROJECT` is set, and otherwise Claude's web search tool when an Anthropic key is set.

Tools the agent defines run by kind: `web_api` tools make a real HTTP request (the model writes the request from the tool's endpoint), while `llm`, `mcp` and `code` tools are played by a model grounded in the tool's description, since MCP and agent-written code have no runtime yet. A network error fails that one call rather than the whole session.

### Apps

An installed app is a `Tool` of kind `app` in that user's memory, so it is saved, exported and restored like everything else, and only installed tools can be called. A model writes the app's functions and oversight levels from its store listing. The agent never asks which app or service to use: it picks one (an app memory says the user uses, otherwise the best-known one). Installing never grants an app's risky functions; those still go through their oversight levels.

Each app records its store `listing` (id, title, developer, icon), its `binding` (how calls run) and its `auth` (what sign-in it would need). Every app is `simulated` for now: a model grounded in the listing plays the app, keeps a history of its calls so later answers stay consistent, and skips sign-in. About one call in five runs into a realistic problem (sold out, no driver, payment declined); the outcome is drawn in code. The binding values `mcp`, `web_api` and `android` are reserved for real backends, and the runner already returns "sign in first" for an app whose auth state is `needed`.

`QUINTESSA_APP_STORE` picks the store:

- `play`: Google Play through the `google-play-scraper` library, with real icons. Needs access to play.google.com.
- `search`: web search limited to Play listings, with no icons.
- `offline`: a bundled catalog of 44 common apps, with no icons.
- `auto` (the default): Play, then web search, then the catalog. A store that fails is skipped.

### Jev

[Jev](https://docs.typesafe.ai/) is a System One decision model: it answers typed questions with probabilities and writes no text. With `QUINTESSA_JEV_API_KEY` set, every user gets four Jev features, each switched from the Jev checkbox and its ▾ menu in the top bar (`PUT /api/preferences`). The choices are saved with the user's state and survive Clear memory; Reset returns to the server's defaults.

- **Shadow next steps** (on by default; `QUINTESSA_DECIDER=llm` starts it off). Each next-step decision is also put to Jev as a Choice over the capabilities and "done", at the same moment as the LLM. The LLM still decides. Jev's pick, probabilities, confidence and latency are kept on the session (`shadow_decisions`), and each step in Traces carries a `Jev p` badge: the probability Jev gave the step the LLM chose, green when Jev's top pick agrees. Each capability's `choose_when` front matter is the criterion Jev reads for it. `uv run python -m quintessa --user ID decisions` prints how often Jev agreed, per choice and by confidence.
- **Let Jev choose the next step** (off by default). The controller's decide call is skipped and the step shows "chosen by Jev" in Traces; the capability still runs on the LLM, with no focus from the controller. If Jev fails, the LLM decides that step. In the shadow studies Jev agreed with Claude on only 34-53% of next steps, so expect different behavior. Driven choices are left out of the agreement report.
- **Ambient filter** (off by default; `QUINTESSA_AMBIENT_FILTER=1` starts it on). Each ambient event and persona replay is first put to Jev as one yes/no question, "does this matter?", with an outline of what the agent is tracking. Below `QUINTESSA_AMBIENT_THRESHOLD` (default 0.3) the session ends with no LLM call and shows as skipped in Traces. What the user says, process progress and the persona profile always run, and a failed Jev call never skips anything. On 60 hand-labeled events (`/mnt/project-files/jev-eval/ambient_events.csv` in the project) it skipped half and missed none that mattered, at about 0.6 s a check against about 6 s for the controller's first decision.
- **Score cards** (on by default). Jev scores each new or changed card's urgency, fit with the user's context now and affinity for the person involved, as three score questions, and rescores every card when the user's location changes. Without it, the agent's own scores rank the brief.

`QUINTESSA_JEV_URL` points Jev at another endpoint with the same `/v1/systemone` API, such as [gev](https://github.com/dglazkov/gev), the open-source one on Gemma.

### Aura personas

`AuraPersonaClient` reads personas, days and observations from the [persona](https://github.com/posttool/persona) Cloud Functions, using the Firebase callable protocol. Set `AURA_PERSONA_BASE_URL` if the functions are not at `https://us-central1-aura-persona.cloudfunctions.net`; for the local emulator, use `http://localhost:5001/aura-persona/us-central1`.

### Where state is kept

Agent state lives in a SQLite database, `data/quintessa.db`; `--data` moves the whole folder. There is no database server to install. Files the agent downloads go in `data/downloads/`, in a folder per user.

- `QUINTESSA_DATABASE_URL` points at another database, such as `postgresql://user:pass@host/quintessa` (install the driver with `uv sync --extra postgres`; Postgres is untested so far). The schema is created and upgraded on first use.
- `QUINTESSA_STATE=file` goes back to the old store, one JSON file per user in `data/agents/`.
- State saved by earlier versions in `data/agents/` is imported on first start, and each file is renamed to `.json.imported`. To go back, rename them and set `QUINTESSA_STATE=file`.
- Run one server per database.

## Command line

```bash
uv run python -m quintessa --user maya say "Jane wants to do dinner at Zuni on Tuesday"
uv run python -m quintessa personas
uv run python -m quintessa --user maya persona <persona-id> --speed 600   # clears maya's agent, then replays a day
uv run python -m quintessa --user maya export maya-agent.json             # download
uv run python -m quintessa --user maya restore maya-agent.json            # restore (any user id works)
uv run python -m quintessa --user maya clear
uv run python -m quintessa --user maya decisions                          # Jev agreement report
uv run python -m quintessa users
uv run python -m quintessa serve --host 127.0.0.1 --port 8000
```

`--models` overrides the model chain for one command. Questions the agent asks are answered in the terminal.

## Web app

```bash
cd web && npm install && npm run build && cd ..
uv run python -m quintessa serve     # http://127.0.0.1:8000
```

For UI work, run `uv run python -m quintessa serve` and `cd web && npm run dev` side by side; Vite proxies `/api` to port 8000.

Every API call names a user with `?user=` or the `X-Quintessa-User` header. The top bar sets it, so two browser tabs with different users have separate agents. The app starts blank.

- **Experience**: a phone with Lock, Discover, Home and Spaces screens, the dynamic island, the brief and an input bar (text and speech).
  - Waiting questions sit in a stacked card at the top of the brief ("1 of N"). Tapping it opens the question sheet, a deck that shows why each question is asked, its topic and section, and for an approval the call it will run. Stashed questions wait in a pile after the brief and come back when their topic changes. The sheet never opens by itself: while questions wait, it peeks in from the bottom edge until the user taps or swipes it up.
  - Tapping a card opens its document in Spaces, focused on the card's section. A card with no document, or with a one-tap action, opens a card sheet with its detail, topic, open questions and action, plus "Not now" and "Dismiss". Tapping the action starts a session that already holds approval for that one tool function.
  - Spaces shows a document's focused sections (chosen by the agent's `device.show_document`, or by a rule: sections with a waiting question, then sections changed since the user last looked, then the first open section with a next step). The rest fold into an outline the user can open one at a time, or all at once with "Show full document"; the user's choice holds until another part of the document changes.
  - The phone renders inside a shadow root with only its skin's stylesheet, so a skin is one CSS file in `web/src/experience/skins/` (`aurora` and `paper` so far).
- **Memory**: the graph as a force-directed layout, topics, documents, facts and permissions.
- **Tools**: installed apps with their icons, functions and sign-in state; a store search to install or uninstall apps yourself; the built-in and agent-made tools.
- **Data**: the global on/off switch (on, with no sources), ambient sources from templates or described in plain words ("vibe coded"), and per-source speed.
- **Traces**: every step of every session, grouped by the input event that started it, with Jev's badge where it was asked. App searches show the candidates, with a check on the ones installed.
- **Top bar**: user, Aura persona picker (clears the user's state and plays a day), Jev on/off and its menu, model chain (pulldowns of Claude and Gemini models, or any `provider:model`) with retries, download and restore of agent state, clear memory, dark and light mode.

## Not built yet

The full list is in [docs/overview.md](docs/overview.md#not-built-yet). The main gaps:

- Real apps and `mcp` and `code` tools. A model plays them for now.
- Memory retrieval: the whole memory snapshot goes into each prompt.
- Resuming a question across a restart: the session is recorded as interrupted, and the next input starts fresh.
- Authentication: the API trusts the user id it is given. It must check identity before it is exposed beyond localhost.
