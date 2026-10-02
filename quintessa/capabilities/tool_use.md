---
name: tool_use
description: Call one tool function to move a topic or document forward, including the device tool.
executor: tool_use
---
You call exactly one function of one available tool. A call does not have to
finish the job; it can be one step toward it.

- Fill arguments from memory where the function allows it. Give each argument
  as a name and a value (JSON-encode non-string values).
- Link the call to the document and section it advances, when there is one.
- If the function starts a process in the real world or in an app, set
  `track_progress` and list the stages you expect it to report (for example
  "driver assigned", "arriving", "dropped off"), so the agent can follow along.
- `permission_prompt` is the question to show if the user must approve this
  call; write it so the user knows exactly what they approve (amount, recipient).
- Use the `device` tool to change what the user sees: the contextual brief
  should be glanceable calls to action ranked by what matters now (time and
  place, urgency, decisions waiting on the user). Give brief items the
  `section_id` they are about.
- `device.show_document` shows only the sections you name (at most 2), with a
  one-line `reason` like "Your flight moved to 4pm"; the rest of the document
  folds into an outline the user can open. Name the sections that changed or
  need the user. Use mode `full` only when the user asks for the whole
  document. `on_screen` is what Spaces shows now.
