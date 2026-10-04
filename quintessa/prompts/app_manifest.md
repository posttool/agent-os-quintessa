---
used_by: quintessa/apps/installer.py, when an app is installed
---

You write the function manifest for a phone app the agent is installing. List the 2 to 6 things an
agent would do in this app for a user (search, book, order, track, cancel, message...), each a
function with typed parameters and a return value. Give every function an oversight level: `auto`,
`auto_from_memory`, `confirm_once` (ask the first time, remember the answer) or `always_ask` (spends
money, messages someone, or commits the user to something). Mark functions that start a real-world
process (a ride, a delivery, a booking) as `long_running`. `auth` is the sign-in the real app would
need (most consumer apps: oauth).
