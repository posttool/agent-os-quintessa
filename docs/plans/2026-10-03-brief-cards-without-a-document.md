# Brief cards without a document

> **Date:** 2026-10-03  
> **Status:** Built with the defaults in [PR #16](https://github.com/posttool/agent-os-quintessa/pull/16) (merged).  
> **Source:** [plan doc](https://claude.ai/code/artifact/885e01df-46ba-4322-8d9f-c8a030ad1b32), copied as written.


## Answer

Yes, it happens. A brief card can point at no document, and tapping it unlocks the phone and jumps to Spaces, which then shows whatever document was already open, an unrelated one, or the empty text "Projects you are working on will show up here". The card's own content is never shown.

## Why it happens

1. **`set_brief` accepts anything.** `_set_brief` in `quintessa/tools/builtin.py:100` stores each item as given. `topic_id`, `document_id` and `section_id` are all optional and never checked, so the agent can send a bare text card, an id it made up, or the id of an archived document.
2. **Many topics have no document.** The memory step creates topics freely but documents only for processes worth tracking (`quintessa/capabilities/memory.md`). In a live Claude run with "Remind me to call mom tonight, confirm tomorrow's 9am dentist, it's raining, bring an umbrella", memory made 3 topics and only 1 document: "Call Mom tonight" and "Rain today" have `document_id: null`. A brief card for either can only carry a `topic_id`, which leads nowhere.
3. **The phone always navigates.** `web/src/experience/Experience.tsx:95` resolves the card to `document_id ?? topic.document_id ?? null` and calls `openDocument`. With `null`, `openDocument` (`Experience.tsx:69`) still unlocks and scrolls to Spaces. Spaces then picks `openDoc ?? first space doc ?? docs[0]` (`Experience.tsx:132`), which has nothing to do with the card. A made-up or archived id lands in the same fallback (archived documents are filtered out at `Experience.tsx:47`), and if the card also had a `section_id`, `POST /api/view` returns 404.

## Plan

1. **A card sheet on the phone.** When a tapped card has no live document, open a sheet over the current screen instead of jumping to Spaces. It shows the card text and, when the card has a topic, the topic's title, summary, what's new, due date and progress. Buttons: "Ask about this" (sends "Tell me more about: \<card text>" to the agent as normal input) and "Close". Opening it marks the topic seen, like opening a document does today. Cards that do have a document keep today's behavior.
2. **Questions in the sheet.** A question card with no document (a choice to make, or an Approve or No for a tool) opens the sheet with the same form Spaces uses. Answering sends the same `POST /api/answer`, so the waiting step resumes, and the sheet closes. Question cards with a document keep today's behavior. Questions get an optional `topic_id` taken from the step's topic, so a topic card's sheet also shows its open questions.
3. **Actions on cards.** `set_brief` items get an optional `action`: tool, function, arguments and a button label like "Call Mom". The server drops the action if the tool isn't installed or the function doesn't exist. The sheet shows the button with the arguments underneath.
4. **A tap starts a pre-approved reasoning step.** Tapping the action starts a new reasoning session whose trigger says the user asked for that action from the brief. The session starts with a granted, session-scoped permission for that one tool function, so when the step calls it, it runs without asking again, "always ask" functions included. Other tools in that session still ask as usual. The result lands where reasoning normally puts it (the document section, the island, a new brief).
5. **Clean up cards on the server.** `_set_brief` fills in `document_id` from the topic when it is missing, and drops ids that don't exist or point at archived documents, while keeping the card. The tool result tells the agent what it fixed (for example "item 2: no document doc-x, kept as a card") so it learns, without failing the step.
6. **Let the agent say more.** Add an optional `detail` field to brief items (one or two sentences) that the sheet shows under the card text. Useful for ambient cards like "bring an umbrella" that have no topic at all.
7. **Prompt.** In `tool_use.md`, ask for a `topic_id` on every brief item, a `detail` when there is no document, and an `action` when the card proposes something the user can just say yes to.
8. **Check it.** Unit tests for the `_set_brief` cleanup, the action check, and the carried approval (a tapped call runs without a new question; a different tool still asks). Then a web build, and screenshots of the sheet from a live run.

## Open decisions (defaults in bold)

1. **How to show a card with no document:** **a sheet over the current screen** / a lightweight page in Spaces / auto-create a stub document for every topic.
2. **Bad ids from the agent:** **keep the card, strip the bad ids and tell the agent** / fail the `set_brief` call.
3. **Optional `detail` field on brief items:** **yes** / no, show topic data only.
4. **Sheet buttons:** **Ask about this + Close** / also Dismiss (removes the card; needs a new endpoint).

Decided by Duke: a tapped action starts a reasoning step that carries the approval for that tool, rather than running the call directly.
