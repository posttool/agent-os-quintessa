# Keep brief cards current, and rank them by salience

> **Date:** 2026-10-03  
> **Status:** Built with the defaults in [PR #19](https://github.com/posttool/agent-os-quintessa/pull/19) (merged).  
> **Source:** Rebuilt from the replies in the "Stale contextual brief cards" project thread. This plan was never a separate document. The ranking rules come from Duke's gist `posttool/943cfb4048205ee733b5b87195d76830`, which couldn't be fetched from the build sandbox; the dimensions below are as recorded in `quintessa/device/salience.py`.

Duke's question: contextual brief cards often stack up and hold stale information after new agent reasoning, new user input, or new incoming information such as location changes or new SMS. How can this be prevented?

The short answer: the agent can't see the brief it already made, and nothing makes it look again when new information arrives.

## Why cards pile up and go stale

1. **The agent can't see the brief.** `set_brief` replaces the whole list, but the brief is never in the agent's context. The memory snapshot and `on_screen` leave it out (`quintessa/executors/common.py:31`). So when it rewrites the brief, it builds from memory and puts old items back.
2. **Nothing triggers a refresh.** A new SMS or location change gets saved to memory, then the session ends. The brief only changes if the model happens to choose a `device.set_brief` step.
3. **Cards are frozen copies.** The text, detail and action arguments are copied when the card is written. Cards have no timestamp, no expiry and no link to the event or topic change that produced them.
4. **Sessions overwrite each other.** Each event starts its own session, and they run in parallel. Each one replaces the whole list from its own view, so the last one to write wins.
5. **Questions never go away.** A pending question waits forever, even after new information answers it, and those cards sit at the top of the brief.

## Plan (defaults in bold)

1. Put the current brief in the agent's context: each card's id, text, topic and age.
2. Replace whole-list writes with per-card edits (add, update by id, remove), saved one at a time. Keep **one card per topic** so a new card replaces the old one for that topic.
3. Give each card the time it was written, an optional `expires_at` for cards like "leave by 3pm", and the event that caused it. The device drops a card once it expires.
4. When a session changes a topic that has a card, run **one quick refresh step at the end of the session**. It keeps, rewrites or removes only the affected cards.
5. That same step can withdraw a pending question once new information answers it.
6. Add tests for two scenarios: a location change updates a "leave now" card, and a text from Mom clears the "Call Mom" card.

Duke said "do it" and this was built as above, plus: open card sheets update live when their card is rewritten, close when it is removed, and say when the card was last updated.

## Ranking by salience (added the same day)

Duke then asked to incorporate his ranking rules, and to consider Jev for ranking where it makes sense.

**Salience dimensions** (from the gist):

- **Urgency:** personal risk if the user does not act (0 to 1).
- **Proximity ("how soon"):** how close in time the event is; nearer scores higher (0 to 1).
- **Relevance ("fit"):** how well the card fits the user's context right now (0 to 1).
- **Affinity ("person"):** how much the person or entity involved matters (0 to 1).
- **Suppression:** a penalty (0 to -1) for cards on topics the user dismissed, snoozed or kept ignoring.

**How it was built:**

- Urgency, relevance and affinity are scored when a card is written. Proximity comes from the card's due time and halves every 2 hours.
- Suppression is a penalty that fades over time: -0.6 for a dismissed topic (half-life 12 hours), -0.3 for a snoozed one (half-life 6 hours), and up to -0.4 for a card left unopened for hours.
- The gist gives no weights, so the thread picked urgency 0.4, proximity 0.25, relevance 0.2 and affinity 0.15.
- **Jev:** scoring against a rubric is what Jev does, and it's fast. At the end of a session, Jev scores urgency, relevance and affinity with three Score questions, for new or changed cards and for every card after a location change. A "score brief cards" checkbox in the Jev menu is on by default when a Jev key is set. If Jev fails, the agent's own scores stay. Jev scoring was only tested against a fake, not live.
- Card sheets gained "Not now" (hides the card for an hour) and "Dismiss", plus a line showing why the card ranks where it does. Cards that open a document have no sheet, so they can't be dismissed yet.
