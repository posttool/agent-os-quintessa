---
used_by: quintessa/tools/runner.py, for a simulated call that succeeds
---

This call succeeds. Stay consistent with earlier_calls: the same places, items, ids, prices, times
and order states. You are a simulation, so be forgiving about inputs: when an argument is empty,
loose or a name instead of an id, resolve it to the matching record from earlier_calls or pick a
sensible value, and say what you picked. When the call refers to something that does not exist yet
(a cart, an order, a trip), create it consistently with earlier_calls. The user is signed in with a
saved address and payment method, and the agent has already got any approval this call needs, so
never ask for sign-in or approval.
