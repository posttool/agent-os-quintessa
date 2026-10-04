# Move agent state into a database

> **Date:** 2026-10-03  
> **Status:** Built with the defaults in [PR #15](https://github.com/posttool/agent-os-quintessa/pull/15) (merged).  
> **Source:** [plan page](https://claude.ai/artifact/NfixAZAqMP63zHNyg8jVCi), converted from HTML to Markdown with the wording kept.

Replace the one-JSON-file-per-user store with SQLite tables, one row per memory item, written incrementally. Per-user isolation, download and restore keep working exactly as they do now.

## How it works today

`AgentHost` keeps each user's `AgentRuntime` in memory and, half a second after any change, serializes the whole thing (`take_snapshot`) and rewrites `data/agents/<hash>.json` through `FileStateBackend`. The snapshot holds the memory graph, topics, documents, tools (with each app's call log), permissions, processes, every raw event, every session trace, device state and preferences.

- Every small change rewrites the user's entire state, and that file only grows: events and traces are never trimmed.
- Nothing can be queried without loading a user's whole state (for example, "all traces that used Jev" or "events from yesterday").
- Downloads from `web.download` land in one shared `data/downloads/` folder, which breaks the per-user rule.
- Which Aura persona a user attached is held only in server memory and is lost on restart.

## The plan

Add a `SqlStateBackend` behind the existing `StateBackend` interface, so the runtime, executors and API don't change. The runtime still works from memory; the database becomes the durable copy and the thing we can query.

### Schema

Each table is keyed by `user_id` first, so every query is scoped to one user. Item bodies are stored as JSON (the same dicts `to_dict` produces today), with a few real columns pulled out for indexing.

| Table | Key | Indexed columns |
| --- | --- | --- |
| `users` | user_id | created_at, saved_at, persona_id, preferences (JSON), device (JSON) |
| `nodes` | user_id, id | type, topic_id, updated_at |
| `edges` | user_id, source, target, type | target |
| `topics` | user_id, id | archived, updated_at |
| `documents` | user_id, id | topic_id, status, updated_at |
| `tools` | user_id, name | kind, binding, listing app id (call log stays in the body) |
| `permissions` | user_id, seq | tool, function, scope |
| `subscriptions` | user_id, id | archived |
| `events` | user_id, id | kind, source, occurred_at |
| `sessions` | user_id, id | status, started_at, has_jev_decisions |
| `schema_version` | | one row; numbered migration steps run on startup |

### Saving only what changed

The debounced save stays, but instead of rewriting everything it compares each item's JSON against a hash of what was last written and upserts only the rows that differ, then deletes rows for items that are gone. All of it runs in one transaction per save, so a crash leaves either the old state or the new one. Hashing rather than relying on the store's change events matters because some code mutates items in place (a session's steps, an app's call log) without emitting an event.

### Loading, download and restore

- **Load** reads the user's rows and rebuilds the same snapshot dict, then calls the existing `apply_snapshot`. Interrupted-session handling is unchanged.
- **Download** is unchanged: `take_snapshot` still produces the `quintessa.agent-state` v1 file, so files downloaded before this change restore after it and vice versa.
- **Restore** validates first (as now), then deletes the user's rows and inserts the new ones in one transaction.

### Moving existing data over

On startup, any `data/agents/*.json` whose user has no row in `users` is imported and the file renamed to `.json.imported`. Nothing is deleted, so going back is just renaming the files.

### Configuration

`QUINTESSA_DATABASE_URL`, defaulting to `sqlite:///data/quintessa.db`. `QUINTESSA_STATE=file` keeps the old file backend available as a fallback. Local running stays `uv run python -m quintessa serve` with no server to install.

### Small fixes that ride along

- Downloads go to `data/downloads/<user hash>/`.
- The attached persona id is saved in `users.persona_id` and reattached on load.

## Open decisions

Each one has a default; say "go with defaults" and it gets built that way.

| Decision | Default | Alternatives |
| --- | --- | --- |
| Which database | SQLite now, written with SQLAlchemy Core (async) so a Postgres URL works later without a rewrite. | Postgres from day one (needs a running server locally); plain stdlib `sqlite3` with no SQLAlchemy dependency (simplest, but Postgres later is a rewrite). |
| How much to normalize | One row per item with a JSON body and a few indexed columns, as in the schema above. | One JSON blob per user in a table (barely better than files); full columns for every field (much more code, migrations on every model change). |
| Keep everything in memory? | Yes, load a user's whole state as today. No behavior change in this PR. | Follow-up: page old events and traces from the database instead of keeping them all in memory and in every snapshot. |
| Retention for events and traces | Keep everything for now. | Keep the last N days (for example 30) and drop older rows on startup. |
| Schema migrations | A `schema_version` table and numbered steps in code. | Alembic, which is worth it once there are several developers or a hosted Postgres. |
| The old file backend | Keep it behind `QUINTESSA_STATE=file` for now; remove it once the database has run for a while. | Remove it in the same PR. |

## Build order

1. Add the schema, the migration runner and `SqlStateBackend` (load, save, delete, list_users).
2. Switch saves to the hash-diff upsert, with restore as a single transaction.
3. Wire it into `build_app` and the CLI, with the env vars and the one-time file import.
4. Fix per-user downloads and persist the persona id.
5. Tests: run the existing host and API tests against both the in-memory and SQLite backends, plus tests for restart, file import, a restore that fails validation leaving data untouched, and two users never seeing each other's rows.
6. README: the new env vars and where the database file lives.

One PR. After pulling: `uv sync`, then restart the server; existing state imports itself on first start.

## Out of scope

- Authenticating the user id in the API. It's still a header or query value; a database doesn't change that, and it remains the open item it was.
- Running more than one server process against the same database. One process per database, as today.
- Moving the server-wide model chain into per-user storage.
