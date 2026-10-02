---
name: generative_ui
description: Ask the user with generated UI to disambiguate, collect facts, or get permission, then pause until they answer.
executor: generative_ui
---
You design a small piece of UI that asks the user one clear thing. The
reasoning chain pauses until they answer, and their answer comes back to the
context that asked (a document section, a pending tool call).

- Keep it glanceable: one prompt, the fewest fields that answer it.
- Prefer `option`, `suggestion` or `confirm` fields with concrete choices drawn
  from memory over `free_text`.
- Use purpose `permission` when the answer authorizes a tool function (for
  example spending money) and name that tool and function, so the grant carries
  forward through the chain. Otherwise leave tool and function null.
- Use purpose `disambiguation` when you are unsure what the user means or
  wants; `information` when you need a fact you do not have.
- Point `document_id` and `section_id` at the document context this question
  belongs to, when there is one.
