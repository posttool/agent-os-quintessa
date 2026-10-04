# Plan: agent installs apps

> **Date:** 2026-10-03  
> **Status:** Built with the defaults in [PR #12](https://github.com/posttool/agent-os-quintessa/pull/12) (merged). Follow-ups: per-user call log for simulated apps in [#13](https://github.com/posttool/agent-os-quintessa/pull/13), a 1-in-5 simulated failure rate in [#17](https://github.com/posttool/agent-os-quintessa/pull/17), and installs without asking in [#20](https://github.com/posttool/agent-os-quintessa/pull/20).  
> **Source:** [plan doc](https://claude.ai/code/artifact/736df439-03e2-45f2-af89-0713aeb1c6ad), copied as written.


## Summary

The agent will search an app store, install the app it needs (with its real name and icon), and only then use it as a tool. Apps run simulated for now, but each installed app records how it would really run and what sign-in it would need, so real apps can replace the simulation later without changing the agent loop.

Why it never installs today (read from the code, not from your traces): the only path to a new tool is `tool_discovery`, which invents an abstract tool definition from scratch. The controller picks it only when "no current tool has the capability", and the `web` tool almost always looks capable enough, so the agent searches the web instead. There is also no notion of an app: no store, no listing, no icon, no install step (`quintessa/executors/tool_discovery_executor.py`, `quintessa/capabilities/_controller.md`).

## Play Store access

Play is blocked from this cloud sandbox: both `play.google.com` and the icon host `play-lh.googleusercontent.com` return 403 from the egress proxy (checked 2026-10-03). On your own machine, where you run `uv run python -m quintessa serve`, both should load normally, and your browser loads icons directly.

So the store sits behind one interface with three backends, picked by `QUINTESSA_APP_STORE` (default `auto` tries them in this order):

| Backend | How it works | Icons | Works in cloud sandbox |
| --- | --- | --- | --- |
| `play` | `google-play-scraper` Python library (search + app details, no API key) | Real Play icon URLs | No |
| `search` | Claude web search limited to `play.google.com`, model extracts package id, title, developer | Usually none, so a letter tile | Yes (search runs on Anthropic's side) |
| `offline` | Bundled catalog of about 40 common apps (dining, delivery, rides, messaging, calendar, travel, shopping) | Real URLs stored, load in your browser | Yes, used by tests |

The live `play` path can only be tested on your machine; tests use the offline catalog and a recorded fake.

## Design

An installed app is a `Tool` with a new kind, `app`, plus three new fields. It lives in the per-user store like every other tool, so it is durable across restarts and included in export/restore.

- **`listing`**: what the store said. Store name, package id (e.g. `com.opentable`), title, developer, icon URL, category, rating, store URL, short description.
- **`binding`**: how calls actually run. `simulated` for every app now: a model grounded in the listing and the app's function list plays the app, exactly like today's `llm` tools. Reserved values for later: `mcp` (server URL), `web_api` (OpenAPI URL), `android` (on-device App Functions / intents). The runner dispatches on binding, so adding a real backend is one new branch in `quintessa/tools/runner.py`.
- **`auth`**: what sign-in the app would need. `{kind: none | oauth | api_key, state: simulated | needed | connected}`. Everything is `simulated` now and the runner ignores it. Later, a call to an app whose state is `needed` returns `needs_user` with a "Sign in to X" prompt instead of running, and credentials go in a per-user secrets store that is left out of exports.

**Function manifest.** Play has no machine-readable list of what an app can do, so at install time a model writes the app's functions (typed parameters, oversight level, long-running flag) from the listing, using the same schema `tool_discovery` already produces. A real binding would later replace this manifest with the one the MCP server or OpenAPI spec reports.

**Install lifecycle**, recorded on the tool and shown in Traces:

1. `discovered`: store search returned it as a candidate.
2. `installing`: manifest being written.
3. `installed`: in the tool list, usable by `tool_use`.
4. Later only: `needs_sign_in` before first real use.
5. `uninstalled`: removed by you or the agent; past traces keep the name.

Only installed tools reach `tool_use`, which already limits its choice to the tools in the store, so a discovered-but-not-installed app can never be called.

## Agent behavior

`tool_discovery` becomes "find and install an app". It runs in two model calls:

1. **Search.** The model turns the step's focus into 1 to 3 store queries ("restaurant reservations", "opentable"). The store returns up to 8 listings per query; already-installed apps are marked.
2. **Choose and install.** The model picks one app (or reuses an installed one), using memory first: if you once said you use Resy, it picks Resy. It writes the function manifest, and the app is installed. Defining a free-form `llm`/`code` tool stays as the fallback when no listing fits.

To make the controller actually pick it, `tool_discovery`'s `choose_when` and the controller guidance change from "no tool has the capability" to: the task is something a person would do in a phone app (book, order, ride, message, pay, schedule, track a delivery) and no installed app does it. `web` stays for finding information, not for acting. Because Jev's `next_step` labels and criteria come from the capability files, Jev sees the same new criterion with no separate change.

Installing is allowed without asking, as you said. Spending, messaging and booking still go through each function's oversight level (`confirm_once`, `always_ask`), so installing an app never grants permission to use its risky functions. The agent can also uninstall an app it no longer needs; it never uninstalls one you installed.

## UI changes

- **Home screen app grid** (`web/src/experience/Experience.tsx`): installed apps show their store icon and title; tools without an icon keep the letter tile. A newly installed app animates in, and the dynamic island says "Installing OpenTable" while it happens.
- **Tools panel**: an "Apps" section above other tools, each card with icon, developer, store link, binding ("simulated"), sign-in state, functions with oversight badges, and Uninstall. A search box queries the same store so you can install an app yourself.
- **Traces**: the install step shows the queries, the candidate listings with icons, which one was chosen and why.
- New API: `GET /api/apps/search?q=`, `POST /api/apps/install`, `DELETE /api/apps/{package}`, all per user.

## Build steps and tests

One PR, in this order:

1. `quintessa/apps/`: `AppListing`, the `AppStore` interface, the `play`, `search` and `offline` backends, and `app_store_from_env()`.
2. Model changes: `ToolKind.APP`, `listing`, `binding`, `auth`, `install_state` on `Tool`, with old snapshots still loading.
3. Runner: dispatch app calls by binding (`simulated` only); auth check stubbed.
4. `tool_discovery` rewrite plus the capability and controller prompt changes.
5. API endpoints, then the Home grid, Tools panel and Traces changes.
6. README: `QUINTESSA_APP_STORE`, and the note that Play only works off the cloud sandbox.

Tests (offline catalog, scripted LLM): search ranks a matching app first; a dinner-booking trigger installs an app and the next `tool_use` step calls it; an uninstalled app cannot be called; installs survive a restart and an export/restore; one user's apps never show up for another user; a store failure falls back to the next backend instead of failing the session. I'll also run one live Claude session here with the `search` backend and post a screenshot of the Home grid.

## Open decisions

Say "try it with defaults" to accept all of these.

| Decision | Default | Alternative |
| --- | --- | --- |
| Ask before installing? | No, install freely; a per-user checkbox "Ask before installing apps" exists, off | Always ask with a card |
| Keep free-form invented tools? | Yes, only when no store app fits | Apps only |
| Separate `app_install` capability? | No, rework `tool_discovery` so Jev's labels stay the same | New fifth capability |
| Store backend | `auto`: Play, then web search, then offline catalog | Pin one with `QUINTESSA_APP_STORE` |
| Preinstalled apps for a new user | None besides `web` and `device` | A starter set (calendar, messaging) |
| Existing invented tools in your saved state | Keep them as they are | Convert matching ones to store apps |
| Icons | Store the Play URL; browser loads it | Server downloads and caches icons per user |
