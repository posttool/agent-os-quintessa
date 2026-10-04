# Plan: every question in the bottom sheet

> **Date:** 2026-10-04  
> **Status:** Approved by Duke on 2026-10-04 and built with the defaults in [PR #21](https://github.com/posttool/agent-os-quintessa/pull/21) (merged). Installs without asking were split out into [#20](https://github.com/posttool/agent-os-quintessa/pull/20).  
> **Source:** [plan doc](https://claude.ai/code/artifact/d9eba0c5-14c3-4fe2-8bde-9ba9ae04e119), copied as written.


## Summary

Every question the agent asks (clarify, choose, approve, install) opens in the same bottom sheet, from wherever the user is, and nowhere else. Today the same question can show up in four places: a "needs you" brief card, loose above Spaces, at the top of a document, and under a document section. After this change those become entry points that open the sheet, and the sheet shows enough context (topic, document section, what will run) to answer without navigating away.

Nothing is built yet. Say "try it with defaults" or "do it" to build with the defaults marked below, or change any decision first.

## Today

The agent asks in three ways that block its session, and a few ways that don't, and each shows up differently.

| Where the ask comes from | What the user sees today | Code |
| --- | --- | --- |
| `generative_ui` step: clarify, collect a fact, or approve (purpose disambiguation, information, permission) | A "needs you" card leads the brief. Tapping it opens Spaces if the question names a live document, else a sheet holding only the form. Also drawn inline: loose above Spaces, at the top of the document, and under its section. A topic card's sheet also lists that topic's questions. | `executors/generative_ui_executor.py`, `web/src/experience/Experience.tsx`, `DocumentView.tsx`, `CardSheet.tsx` |
| `tool_use` permission gate before a tool function that isn't auto | Same as above, labeled "Needs your OK" with only the model's `permission_prompt`; the call's arguments are not shown | `executors/tool_use_executor.py:89` |
| `tool_discovery` asking before installing apps | Being removed: Duke decided on 2026-10-04 that the agent installs apps without asking (the "Agent installs apps as tools" thread is making that change), so this plan leaves installs out | `executors/tool_discovery_executor.py:97` |
| Brief card with an action (the agent proposes, the tap approves) | Already the sheet: action button plus tool and arguments | `CardSheet.tsx` |
| Questions that went stale | Withdrawn at session end; the card and form vanish | `loop/brief_refresh.py` |
| App needs sign-in (`needs_user`) | Never shown; it is only a tool result in the trace. Unreachable today since all apps are simulated | `tools/runner.py:113` |
| Agent asks in a notification or card text | Possible, since nothing tells it not to, but the user can't answer it | `tools/builtin.py` notify, brief cards |
| CLI | Terminal prompt | `cli.py:26` |

Two inconsistencies worth fixing on the way. A question's "Not now" answers it as dismissed, so the agent moves on without it, while a card's "Not now" hides it for an hour. And the sheet for a question hides its topic context (`asksOnly`), so the user sees the prompt with nothing around it.

## The design

One component, the question sheet, is the only place an answer form is drawn. Everything else points at it.

**How it opens**

1. Tapping a "needs you" card opens the sheet, always, even when the question names a document (today that jumps to Spaces).
2. In Spaces, where a form is drawn today, a one-line "Waiting on you: \<prompt>" row appears instead, under the section that asked. Tapping it opens the sheet.
3. Tapping the dynamic island while it says "Waiting for you" opens the oldest waiting question.
4. When the user just asked for something (typed or spoke in the last minute) and that session asks a question, the sheet opens by itself, unless another sheet is already open.
5. A topic card's sheet keeps listing that topic's questions, so a card and its questions stay together.

**What it shows, top to bottom**

- A kind label: "Quick question" or "Needs your OK".
- The prompt, then one line of why the agent is asking (new field, written by the model).
- Context: topic title and summary, and when the question names a document section, that section's title and overview. "Open document" goes to Spaces focused on it.
- For an approval: the tool, function and arguments that will run, the same way a card action shows them today.
- The form: options as full-width rows, with an "Something else" free-text row on option questions; free text, number and location fields as today.
- Buttons: the answer ("Send", or "Approve"/"Install" and "No"), "Skip" (the agent goes on without an answer, what "Not now" does today), "Stash" (put it aside for later, below), and "Close" (the question keeps waiting where it was).

**Stacking several questions**

- When two or more questions wait, the brief shows one stacked "needs you" card ("3 questions") with two cards peeking behind it, instead of a row per question.
- Tapping it opens the sheet as a deck: the top question is full size, the next two peek out below it, and a "1 of 3" count sits on top. Order is the question the user tapped (or the auto-opened one) first, then the rest of its topic, then the others oldest first.
- Answering, skipping or stashing the top card slides the next one up. Swiping sideways moves through the deck without answering.
- A question answered, withdrawn or skipped elsewhere drops out of the deck live, as cards do now.

**Stashing**

- "Stash" puts the top question aside. It keeps waiting (the agent's session stays paused on it) but leaves the needs-you stack, never auto-opens, and the island stops pointing at it.
- Stashed questions sit in a pile: a small "2 stashed" chip at the end of the brief. Tapping it opens the same deck holding just the stash.
- A stashed question comes back to the stack by itself when its topic gets new information, since that is when it may matter again. The end-of-session refresh can still withdraw it.
- The stash is saved with the device state, so it survives a reload, and the agent sees which waiting questions are stashed so it doesn't ask them again.
- "Stash all" on the deck puts every remaining question aside at once.

## Decisions

Each row lists the default first; the build uses it unless you pick another.

| # | Decision | Default | Alternatives |
| --- | --- | --- | --- |
| 1 | Forms inside documents in Spaces | **Replace with a "Waiting on you" row that opens the sheet** | Keep inline forms as well |
| 2 | Sheet opens by itself | **Only for a session the user started in the last minute, when no sheet is open** | Never (card and island only); always |
| 3 | Island tap | **Opens the oldest waiting question** | Island stays display only |
| 4 | "Not now" on a question | **Becomes "Skip" (agent proceeds without it); "Close" leaves it waiting** | Snooze the question card for an hour while the session keeps waiting |
| 5 | Context in a question sheet | **Topic summary plus the document section it names** | Prompt only, as today |
| 6 | Why the agent is asking | **New `context` field on every question, one sentence** | None |
| 7 | Approvals show what will run | **Yes: tool, function, arguments** | Prompt only |
| 8 | Free answer on option questions | **"Something else" row on every option question** | Only when the model adds a free\_text field |
| 9 | Several waiting questions | **A deck: one stacked card in the brief, the sheet shows one question with the next two peeking, "1 of N", same topic first** | A card per question in the brief; all forms in one scroll |
| 10 | Asking in notifications or card text | **Prompts tell the agent never to; questions go through generative\_ui** | Leave prompts as they are |

Stash decisions:

| # | Decision | Default | Alternatives |
| --- | --- | --- | --- |
| 12 | What a stashed question does to the agent | **Keeps its session paused, out of the brief stack** | Counts as skipped so the agent goes on, and is asked again later |
| 13 | When a stashed question comes back | **When its topic gets new information; otherwise only when the user opens the stash** | After a fixed time, such as 4 hours; never |
| 14 | Where the stash lives | **A "N stashed" chip at the end of the brief** | A drawer in Spaces; behind the island |

## Build steps

One PR, server first, then web.

1. **Question model.** `UXRequest` gains `context` (why it asks) and `arguments` (what an approval runs). The `generative_ui` schema adds `context`; strict schemas mean scripted test outputs gain it too.
2. **Approvals carry what runs.** `tool_use` fills `arguments` and sets `context` from the call's rationale.
3. **Prompts.** `generative_ui.md` asks for `context`; `_controller.md` and `tool_use.md` say never to ask in a notification or card text.
4. **Question sheet.** A `QuestionSheet` (or a question mode of `CardSheet`) with context, call preview, a deck of waiting questions (top card, two peeking, "1 of N", swipe through), "Skip", "Stash", "Stash all" and "Close"; a stacked needs-you card in the brief and a "N stashed" chip that opens the stash. `UXForm` drops its own buttons and "Not now" in favour of the sheet's, and gains the "Something else" row.
5. **Entry points.** `tapCard` always opens the sheet for a question card; `Experience.tsx` and `DocumentView.tsx` swap inline forms for "Waiting on you" rows; the island becomes tappable; auto-open for a session the user just started (the server marks which questions come from a user-triggered session in the last minute).
6. **Stash state.** The device state keeps `stashed_ux_ids`, saved per user; `POST /api/ux/{id}/stash` and `/unstash`; a topic update unstashes its questions; `questions_waiting` marks stashed ones for the agent.
7. **Checks.** Python tests for the new fields, skip vs. stash vs. close, and a topic change unstashing its question; `npm run build`; screenshots of a clarifying question, an approval, a three-question deck and the stash in both skins, on the lock screen and in Spaces.

After pulling: `npm run build` in web/, restart the server.

## Out of scope

- Questions that don't block the session. Every question still pauses its session until answered, skipped or withdrawn.
- Questions surviving a server restart; waiting sessions are still dropped on restore.
- App sign-in as a sheet question; no app can need sign-in until real app bindings exist.
- Answering a waiting question by typing in the input bar; typed text still starts a new session.
- The CLI keeps its terminal prompt.
