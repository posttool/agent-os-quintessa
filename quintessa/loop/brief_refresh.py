"""Keeps the contextual brief true. A card is a snapshot of a topic; when the
topic changes after the card was written (a new text, a new location, the
user's own answer), the card is stale. At the end of each reasoning session
one model call looks at just the stale cards, and at questions still waiting
on topics that changed, and keeps, rewrites or removes them."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from quintessa.clock import now, parse_time
from quintessa.context import JSON_INSTRUCTION, Staleness, card_view, staleness
from quintessa.device.salience import Salience, clamp
from quintessa.llm import schema as s
from quintessa.models import InputKind, Question, ReasoningSession, TraceStep
from quintessa.serde import to_dict

if TYPE_CHECKING:
    from quintessa.loop.runtime import AgentRuntime

log = logging.getLogger(__name__)

PURPOSE = "brief_refresh"
SCORE = "score_cards"

INSTRUCTIONS = """You keep a personal agent's contextual brief true. Each card \
in `cards` was written before something changed in its topic (`changed` says \
what is known now). For each card decide:
- "keep" when it still says the right thing,
- "rewrite" when it should say something else now (give the new text, detail, \
urgency, expires_at and salience scores; set drop_action when its one-tap \
action no longer fits),
- "remove" when it no longer applies (done, answered, cancelled, past).
Each question in `questions` is still waiting on the user, but its topic \
changed after it was asked. Withdraw it only when what is now known answers \
it or makes it moot. Use `memory` and `trigger` for what changed. Give a short \
reason for each decision."""

SCHEMA = s.obj(
    {
        "cards": s.array(
            s.obj(
                {
                    "id": s.string(),
                    "verdict": s.enum_of(["keep", "rewrite", "remove"]),
                    "text": s.string("New text when rewriting; empty otherwise."),
                    "detail": s.string(),
                    "urgency": s.string(),
                    "expires_at": s.nullable(s.string("ISO time the card stops applying, or null.")),
                    "drop_action": s.boolean(),
                    "salience": s.nullable(
                        s.obj(
                            {
                                "urgency": s.number("Personal risk if the user does not act, 0 to 1."),
                                "relevance": s.number("How well it fits the user's context now, 0 to 1."),
                                "affinity": s.number("How much the person or business involved matters, 0 to 1."),
                            }
                        )
                    ),
                    "reason": s.string(),
                }
            )
        ),
        "questions": s.array(s.obj({"id": s.string(), "withdraw": s.boolean(), "reason": s.string()})),
    }
)


def _stale_questions(runtime: AgentRuntime) -> list[Question]:
    store = runtime.store
    stale = []
    for request in runtime.questions.pending.values():
        topic = store.topics.get(request.topic_id) if request.topic_id else None
        if topic is not None and topic.updated_at > request.created_at:
            stale.append(request)
    return stale


async def refresh_brief(runtime: AgentRuntime, session: ReasoningSession) -> TraceStep | None:
    """Settle stale cards and questions after a session. Cards whose topic is
    gone are removed outright; the rest are asked about in one model call.
    Returns the trace step, or None when nothing was stale."""
    device = runtime.device
    device.prune_brief(now())
    gone = [b for b in device.state.brief if staleness(runtime.store, b).gone]
    lines = [f"removed {b.id} ({b.text}): {staleness(runtime.store, b).value}" for b in gone]
    device.remove_cards([b.id for b in gone])

    cards = [b for b in device.state.brief if staleness(runtime.store, b) != Staleness.FRESH]
    questions = _stale_questions(runtime)
    if not cards and not questions:
        return _step(session, lines) if lines else None

    seen = {b.id: b.updated_at for b in cards}
    topics = {t: runtime.store.topics[t] for t in {b.topic_id for b in cards} | {q.topic_id for q in questions} if t}
    payload = {
        "trigger": {"kind": session.trigger.kind, "content": session.trigger.content},
        "now": now(),
        "cards": [{**to_dict(card_view(b)), "changed": _topic(topics.get(b.topic_id))} for b in cards],
        "questions": [
            {"id": q.id, "prompt": q.prompt, "asked_at": q.created_at, "changed": _topic(topics.get(q.topic_id))}
            for q in questions
        ],
        "memory": runtime.store.snapshot(),
    }
    step = _step(session, lines)
    try:
        result = await runtime.llm.generate_json(
            system=f"{INSTRUCTIONS}\n\n{JSON_INSTRUCTION}",
            prompt=json.dumps(payload, indent=1, default=str),
            schema=SCHEMA,
            purpose=PURPOSE,
        )
    except Exception as e:  # the session's own work stands; the trace shows the refresh failed
        log.exception("brief refresh after %s failed", session.id)
        step.error = f"{type(e).__name__}: {e}"
        step.ended_at = now()
        return step
    step.model = result.model
    lines += _apply_cards(runtime, result.data["cards"], seen)
    lines += _apply_questions(runtime, result.data["questions"], {q.id for q in questions})
    step.output = result.data
    step.summary = "; ".join(lines) or "nothing to change"
    step.ended_at = now()
    return step


def _apply_cards(runtime: AgentRuntime, verdicts: list[dict[str, Any]], seen: dict) -> list[str]:
    device = runtime.device
    lines = []
    for v in verdicts:
        card = next((b for b in device.state.brief if b.id == v["id"]), None)
        if card is None or v["id"] not in seen or card.updated_at != seen[v["id"]]:
            continue  # not asked about, or another session changed it meanwhile
        if v["verdict"] == "remove":
            device.remove_cards([card.id])
            lines.append(f"removed {card.id} ({card.text}): {v['reason']}")
            continue
        if v["verdict"] == "rewrite":
            old = card.text
            card.text = v["text"] or card.text
            card.detail = v["detail"]
            card.urgency = v["urgency"] or card.urgency
            card.expires_at, _ = parse_time(v.get("expires_at"))
            if v.get("drop_action"):
                card.action = None
            if v.get("salience"):
                card.salience = Salience(
                    clamp(v["salience"].get("urgency"), 0.4),
                    clamp(v["salience"].get("relevance"), 0.5),
                    clamp(v["salience"].get("affinity"), 0.5),
                )
            lines.append(f"rewrote {card.id} ({old} -> {card.text}): {v['reason']}")
        else:
            lines.append(f"kept {card.id} ({card.text})")
        card.updated_at = now()
        device.put_brief(card)
    return lines


def _apply_questions(runtime: AgentRuntime, verdicts: list[dict[str, Any]], asked: set[str]) -> list[str]:
    lines = []
    for v in verdicts:
        if v["withdraw"] and v["id"] in asked and runtime.questions.withdraw(v["id"], v["reason"]):
            lines.append(f"withdrew question {v['id']}: {v['reason']}")
    return lines


def _step(session: ReasoningSession, lines: list[str]) -> TraceStep:
    step = TraceStep(
        len(session.steps), PURPOSE, "Keep the brief true after this session", "cards or questions went stale"
    )
    step.summary = "; ".join(lines)
    step.ended_at = now()
    session.steps.append(step)
    return step


def _topic(topic) -> dict[str, Any] | None:
    if topic is None:
        return None
    return {
        "title": topic.title,
        "summary": topic.summary,
        "new_info": topic.new_info,
        "due": topic.due,
        "progress_note": topic.progress_note,
        "updated_at": topic.updated_at,
    }


async def score_cards(runtime: AgentRuntime, session: ReasoningSession) -> TraceStep | None:
    """Have Jev score the cards it has not scored since they were written,
    or every card when the user's location changed (what fits now moved)."""
    scorer = runtime.active_card_scorer
    if scorer is None:
        return None
    moved = session.trigger.kind == InputKind.LOCATION
    cards = [b for b in runtime.device.state.brief if moved or b.salience.scored_at != b.updated_at]
    if not cards:
        return None
    step = TraceStep(
        len(session.steps),
        SCORE,
        "Score the brief: urgency, fits now, person",
        "the user moved" if moved else "cards changed since they were scored",
        model=scorer.client.label,
    )
    session.steps.append(step)
    step.summary = "; ".join(await scorer.score(runtime, cards))
    runtime.device.brief_scores_changed()
    step.output = {"order": [{"text": b.text, "score": b.salience.score} for b in runtime.device.state.brief]}
    step.ended_at = now()
    return step
