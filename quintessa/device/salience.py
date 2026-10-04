"""Ranks brief cards by salience, after Duke's salience dimensions
(gist posttool/943cfb4048205ee733b5b87195d76830):

  urgency      personal risk if the user does not act (0-1)
  proximity    how close in time the event is; nearer scores higher (0-1)
  relevance    how well the card fits the user's context right now (0-1)
  affinity     how much the person or entity involved matters (0-1)
  suppression  a penalty (0 to -1) for cards on topics the user dismissed,
               snoozed or kept ignoring

The agent (or Jev, when the user has Jev ranking on) scores urgency,
relevance and affinity when a card is written. Proximity and suppression
are computed here from the clock, so the order keeps moving as time passes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from quintessa.clock import now

WEIGHTS = {"urgency": 0.4, "proximity": 0.25, "relevance": 0.2, "affinity": 0.15}

# The urgency label the agent gives a card stands in for a score it left out.
LABEL_URGENCY = {"urgent": 0.9, "high": 0.7, "normal": 0.4, "low": 0.15}

# Proximity: 1 when the event is now (or just passed), halving every PROXIMITY_HALF_LIFE.
PROXIMITY_HALF_LIFE = timedelta(hours=2)

# Suppression: a dismissal or a snooze starts at its penalty and fades by half
# every half-life. An unopened card starts losing after IGNORE_GRACE and
# reaches IGNORE_MAX over IGNORE_RAMP; a rewrite starts the clock again.
DISMISS_PENALTY, DISMISS_HALF_LIFE = -0.6, timedelta(hours=12)
SNOOZE_PENALTY, SNOOZE_HALF_LIFE = -0.3, timedelta(hours=6)
IGNORE_GRACE, IGNORE_RAMP, IGNORE_MAX = timedelta(hours=2), timedelta(hours=10), -0.4


@dataclass
class Salience:
    urgency: float | None = None
    relevance: float = 0.5
    affinity: float = 0.5
    proximity: float = 0.0
    suppression: float = 0.0
    score: float = 0.0
    scored_by: str = "agent"  # who scored urgency, relevance and affinity: "agent", or the Jev model
    scored_at: datetime | None = None  # the card's updated_at when Jev scored it


@dataclass
class Suppression:
    """The user pushed a card away. Kept per topic (or per card text when it
    has none), so a new card on the same topic still ranks lower for a while."""

    key: str
    kind: str  # "dismissed" | "snoozed"
    at: datetime = field(default_factory=now)


def card_key(topic_id: str | None, text: str) -> str:
    return f"topic:{topic_id}" if topic_id else f"text:{text.strip().lower()}"


def clamp(value: object, default: float) -> float:
    try:
        return min(max(float(value), 0.0), 1.0)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def proximity(due_at: datetime | None, at: datetime) -> float:
    if due_at is None:
        return 0.0
    ahead = max((due_at - at).total_seconds(), 0.0)
    return 0.5 ** (ahead / PROXIMITY_HALF_LIFE.total_seconds())


def suppression(
    key: str, opened_at: datetime | None, updated_at: datetime, suppressions: list[Suppression], at: datetime
) -> float:
    penalty = 0.0
    for s in suppressions:
        if s.key != key:
            continue
        base, half = (
            (DISMISS_PENALTY, DISMISS_HALF_LIFE) if s.kind == "dismissed" else (SNOOZE_PENALTY, SNOOZE_HALF_LIFE)
        )
        penalty += base * 0.5 ** (max((at - s.at).total_seconds(), 0.0) / half.total_seconds())
    since = at - max(updated_at, opened_at) if opened_at else at - updated_at
    if since > IGNORE_GRACE:
        penalty += IGNORE_MAX * min((since - IGNORE_GRACE) / IGNORE_RAMP, 1.0)
    return max(penalty, -1.0)


def score(s: Salience, label: str) -> float:
    urgency = s.urgency if s.urgency is not None else LABEL_URGENCY.get(label, 0.4)
    total = (
        WEIGHTS["urgency"] * urgency
        + WEIGHTS["proximity"] * s.proximity
        + WEIGHTS["relevance"] * s.relevance
        + WEIGHTS["affinity"] * s.affinity
    )
    return round(total + s.suppression, 4)
