"""What the user does with a card in the brief: open it, dismiss it, snooze it,
or tap its action."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from quintessa.api.deps import Agent
from quintessa.clock import now
from quintessa.loop.runtime import AgentRuntime

router = APIRouter(prefix="/api")


@router.post("/cards/{card_id}/open")
async def brief_open(card_id: str, agent: AgentRuntime = Agent) -> dict[str, Any]:
    """The user opened a card, so it is not being ignored."""
    return {"ok": agent.device.open_card(card_id)}


@router.post("/cards/{card_id}/dismiss")
async def brief_dismiss(card_id: str, agent: AgentRuntime = Agent) -> dict[str, Any]:
    """Swiped away: gone, and its topic ranks lower for a while."""
    if agent.device.dismiss_card(card_id) is None:
        raise HTTPException(404, "that card is no longer in the brief")
    return {"ok": True}


@router.post("/cards/{card_id}/snooze")
async def brief_snooze(
    card_id: str, minutes: int = Query(60, ge=1, le=7 * 24 * 60), agent: AgentRuntime = Agent
) -> dict[str, Any]:
    """ "Not now": back in the brief after `minutes`, ranked a little lower."""
    card = agent.device.snooze_card(card_id, now() + timedelta(minutes=minutes))
    if card is None:
        raise HTTPException(404, "that card is no longer in the brief")
    return {"ok": True, "until": card.snoozed_until}


@router.post("/cards/{card_id}/act")
async def brief_act(card_id: str, agent: AgentRuntime = Agent) -> dict[str, Any]:
    """The user tapped a brief card's action; the tap is their approval."""
    session = agent.start_card_action(card_id)
    if session is None:
        raise HTTPException(404, "that card or its action is no longer in the brief")
    return {"session_id": session.id}
