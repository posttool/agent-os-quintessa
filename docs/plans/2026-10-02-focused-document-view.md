# Plan: Focused document view in the Experience panel

> **Date:** 2026-10-02  
> **Status:** Built with the defaults in [PR #6](https://github.com/posttool/agent-os-quintessa/pull/6) (merged).  
> **Source:** [plan doc](https://claude.ai/code/artifact/de4e746a-fe0a-4680-ae07-1003b68077ca), copied as written.


## Summary

Spaces should open a document showing only the one or two sections that matter right now, with everything else folded into a one-line outline the user can tap open. The agent picks the focus, a simple rule fills in when it hasn't, and the user can expand any section, the whole document, or ask for one by voice or text at any time.

- **Focused by default:** title, status, one line of progress, a short "why you're seeing this" line, then the focused sections in full.
- **Everything else one tap away:** remaining sections appear as a compact outline (title and status chip). Tapping one expands it in place; "Show full document" expands all.
- **Ask for anything:** "show me the substitution section" or "open the whole trip doc" from the input bar routes to the same view.
- **The agent knows what's on screen:** the current focus is passed into the reasoning loop, so the agent stops re-showing what the user already sees and doesn't fight a section the user opened themselves.

## How it works today

The pieces for focus exist, but the UI ignores them: every document renders top to bottom in full, and the focused section only gets a highlight.

| Piece | Where | What it does now |
| --- | --- | --- |
| Document model | `quintessa/models/document.py`, `document_section.py` | Title, status, progress overview, sections (overview, details, done, next), key dates, observations, links. Sections have no timestamps, so there's no way to tell which one changed. |
| Focus state | `quintessa/device/device_state.py` | One global `focused_document_id` and `focused_section_id`. No reason, no multi-section focus, no record of who set it. |
| Agent sets focus | `device.show_document` in `quintessa/tools/builtin.py` | Takes a document and an optional single section. |
| Answers return to context | `close_ux` in `quintessa/device/surface.py`, called from `reasoning_loop.py` | After a question is answered, focuses the document and section that asked. This already matches the spec's "return to the context, a document section". |
| Rendering | `web/src/experience/DocumentView.tsx` | Renders every section, all key dates, observations and links. Focused section gets a `focus` CSS class only. |
| Opening docs | `Experience.tsx` | Brief items and Space tabs open a whole document. Brief items carry no section. |
| What the agent sees | `executors/common.py` | Memory snapshot and the trigger. The agent never learns what is on screen. |

The spec backs the change: the brief should be "glanceable with call to action rather than complete details", Spaces is where "the user can ask for them by topic", and an answered question should "return to the context, a document section" and rerender "the target section" (`docs/spec.md`, Experience and Generative UI sections).

## Proposed design

Focus becomes a small per-document record that the agent, a fallback rule, or the user can set, and the UI renders from it.

### 1. A focus record per document

Replace the single global section focus with a `DocumentFocus` per document in `DeviceState`:

- `section_ids`: up to 2 sections to show expanded (a list, so "flight changed, hotel affected" can show both).
- `mode`: `focused` or `full`.
- `reason`: one short line shown above the sections, e.g. "Your flight moved to 4pm".
- `set_by`: `agent`, `rule` or `user`, plus `updated_at`.

`focused_document_id` stays as the document Spaces opens to. Focus is saved with the rest of the device state, so it survives restarts and export/restore.

### 2. Who decides the focus, in priority order

1. **The user.** Anything the user expands or asks for wins until a new trigger touches that document.
2. **The agent.** `device.show_document` takes `section_ids`, `mode` and `reason`. Answering a question keeps focusing the section that asked, as it does today.
3. **A fallback rule** when neither has set one, no LLM call: sections with a pending question first, then sections changed since the user last looked, then the first section that isn't complete and has next actions. If nothing qualifies, show the progress overview and the outline only.

The rule needs one model change: `updated_at` on `DocumentSection`, set in `_upsert_section` only when content actually changes.

### 3. What the focused view shows

- Header: title, status chip, one line of progress overview.
- The reason line.
- Pending questions for this document (always shown, they need the user).
- Focused sections, in full.
- **Outline** of the other sections: title plus status chip, one row each, with a dot on any that changed. Tap to expand in place; tap again to fold.
- Key dates: only the next upcoming one, with "All dates" to expand.
- Observations and links folded under "More".
- A "Show full document" toggle at the bottom, and "Back to focus" while in full mode.

### 4. Calling up anything on demand

- **Tap:** outline rows, "Show full document" and Space tabs change the view instantly in the browser, then tell the server through a new `POST /api/view` so the choice is saved as user focus. No reasoning session runs.
- **Ask:** "show me the substitution section" or "open the whole trip" goes through the input bar to the controller, which calls `device.show_document` with the right sections or `mode: full`. The controller and tool-use prompts get a line saying so.
- **Brief items:** `BriefItem` gains `section_id`, so tapping "Flight moved" opens the trip focused on the flight section rather than the top of the doc.

### 5. The agent sees what's on screen

Add the current device view (open document, focus, mode) to the context every capability receives in `executors/common.py`. That lets the agent skip re-showing what's already open and respect a section the user opened themselves.

## Implementation steps

One PR, built in this order, each step with tests using the scripted LLM.

1. **Models.** Add `DocumentFocus` (new file in `quintessa/device/`), a `focus` map on `DeviceState`, `section_id` on `BriefItem`, `updated_at` on `DocumentSection`. Old saved states load with empty defaults.
2. **Memory.** `_upsert_section` in `quintessa/memory/apply.py` stamps `updated_at` when a field changes.
3. **Surface.** `DeviceSurface.show_document` takes `section_ids`, `mode`, `reason`, `set_by`. `close_ux` passes the asking section as agent focus. A `resolve_focus(doc)` helper applies the fallback rule.
4. **Device tool.** Extend `device.show_document` parameters and validate section ids against the document; extend `set_brief` items with `section_id`.
5. **Context.** Add the on-screen view to `session_context` in `executors/common.py`. One line each in `_controller.md` and `tool_use.md` about focusing sections and handling "show me X" requests.
6. **API.** `POST /api/view` with `document_id`, `section_ids`, `mode`; records user focus and emits a device event.
7. **Web.** Split `DocumentView.tsx` into a focused view, an outline row component and the full view. `Experience.tsx` reads focus per document, passes brief `section_id`, and calls `/api/view` on taps. Styling for the outline in each skin.
8. **Check it live.** Run the Jane dinner flow and a synthetic persona day with Claude and confirm documents open focused, the outline expands, and "show me everything" works.

Tests to add: fallback rule ordering, user focus surviving an unrelated trigger and yielding to a related one, answered question focusing its section, `/api/view` persistence and export/restore round trip, invalid section ids rejected by the device tool.

## Decisions for Duke

Each has a default the plan uses if you don't weigh in.

| Question | Default | Alternative |
| --- | --- | --- |
| How many sections expanded at once? | Up to 2 | Exactly 1 |
| When does user focus give way to the agent? | When a new trigger touches that document | Never until the user leaves the document |
| Should collapsed sections show a one-line overview? | No, title and status only | Title, status and first line of overview |
| Should taps run the reasoning loop? | No, taps are recorded but don't start a session | Each tap is an input the agent can react to |
| Apply focus to the Spaces tab strip too (hide quiet docs)? | Not in this change | Show only docs with activity, rest under "All" |
