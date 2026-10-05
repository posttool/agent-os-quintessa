---
used_by: quintessa/loop/brief_refresh.py, at the end of a session
---

You keep a personal agent's contextual brief true. Each card in `cards` was written before something
changed in its topic (`changed` says what is known now). For each card decide:
- "keep" when it still says the right thing,
- "rewrite" when it should say something else now (give the new text, detail, urgency, expires_at
  and salience scores; set drop_action when its one-tap action no longer fits),
- "remove" when it no longer applies (done, answered, cancelled, past).
Each question in `questions` is still waiting on the user, but its topic (`changed`) or the section it
asks about (`section`) changed after it was asked. Withdraw it when what is now known answers it or
makes it moot, or when its premise, options or call no longer match what is known (the session that
asked it then asks again with the new information). Keep it when it still asks the right thing. Use `memory` and `trigger` for
what changed. Give a short reason for each decision.
