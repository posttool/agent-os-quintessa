---
used_by: the card parameters of the device tool (set_brief, update_brief)
---

A card is {text, topic_id, document_id, section_id, urgency, detail, action, expires_at, due_at,
salience}; detail is one or two sentences shown when the card has no document; action is optional
{tool, function, arguments: {name: value}, label} for a card the user can just say yes to;
expires_at is an ISO time after which the card no longer applies ("leave by 3pm"), or omit it;
due_at is the ISO time the thing the card is about happens (the meeting, the delivery), or omit it;
salience is {urgency, relevance, affinity}, each 0 to 1: urgency is the personal risk if the user
does not act (0.7-1 hard commitments like a meeting starting, a gate change, a courier outside;
0.3-0.7 perishable windows like rain in minutes, a 2FA code, a missed important call; 0-0.3 routine
FYIs), relevance is how well it fits where the user is and what they are doing now, affinity is how
much the person or business involved matters to the user. The brief is ordered by these
