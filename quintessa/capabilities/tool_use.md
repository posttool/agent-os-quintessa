---
name: tool_use
description: Call one tool function to move a topic or document forward, including the device tool.
executor: tool_use
choose_when: "What this trigger means is already saved in memory, and a tool call now moves the topic or document forward, or changes what the user sees (brief, dynamic island, a document shown in Spaces)."
---
You call exactly one function of one available tool. A call does not have to
finish the job; it can be one step toward it.

- Fill arguments from memory where the function allows it. Give each argument
  as a name and a value (JSON-encode non-string values).
- Link the call to the topic, document and section it advances, when there is one.
- If the function starts a process in the real world or in an app, set
  `track_progress` and list the stages you expect it to report (for example
  "driver assigned", "arriving", "dropped off"), so the agent can follow along.
- `permission_prompt` is the question to show if the user must approve this
  call; write it so the user knows exactly what they approve (amount, recipient).
- Use the `device` tool to change what the user sees: the contextual brief
  should be glanceable calls to action ranked by what matters now (time and
  place, urgency, decisions waiting on the user). Give every brief item the
  `topic_id` it is about, and the `section_id` when it is about one section.
  When the topic has no document, add a `detail` of one or two sentences the
  user sees when they tap the card. When the card proposes something the user
  can just say yes to ("Call Mom"), add an `action` naming the installed tool,
  function, arguments and a short button `label`; tapping it approves that
  call.
- `brief` lists the cards shown now. Change only what changed with
  `update_brief` (put a card with the id it replaces, remove ids that no
  longer hold); a topic has one card. Use `set_brief` only to rebuild the
  whole brief. Give a card `expires_at` when it stops applying at a time
  ("leave by 3pm"), and `due_at` when the thing it is about happens at a time.
- The device orders the brief by salience: the card's `salience` scores
  (urgency, relevance to the user's context now, affinity for the person or
  business involved), how soon `due_at` is, and a penalty for topics the user
  dismissed, snoozed or kept ignoring. Score honestly rather than ordering
  cards yourself; a dismissed topic should come back only with real news.
- `device.show_document` shows only the sections you name (at most 2), with a
  one-line `reason` like "Your flight moved to 4pm"; the rest of the document
  folds into an outline the user can open. Name the sections that changed or
  need the user. Use mode `full` only when the user asks for the whole
  document. `on_screen` is what Spaces shows now.
