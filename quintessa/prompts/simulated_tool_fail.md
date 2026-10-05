---
used_by: quintessa/tools/runner.py, for a simulated call that runs into a problem
---

This call runs into one realistic problem that a real app has now and then, such as an item selling
out, no table or driver available, a declined payment, a closed store or the service being busy.
Report it specifically, as `failed`, or as `needs_user` when the user has to choose something. Don't
blame the arguments. Stay consistent with earlier_calls: the same places, items, ids, prices, times
and order states.
If the problem offers alternatives to choose from, `pictures` may show them, one per item, captioned
with the item's name; otherwise leave `pictures` empty.
