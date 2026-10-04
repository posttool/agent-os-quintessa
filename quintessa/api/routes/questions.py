"""Answering, stashing and unstashing the questions a session waits on."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from quintessa.api.bodies import AnswerBody
from quintessa.api.deps import Agent
from quintessa.loop.runtime import AgentRuntime
from quintessa.models import Answer

router = APIRouter(prefix="/api")


@router.post("/questions/{question_id}")
async def answer(question_id: str, body: AnswerBody, agent: AgentRuntime = Agent) -> dict[str, Any]:
    response = Answer(question_id, body.values, body.dismissed, body.surface_context)
    if not agent.answer(response):
        raise HTTPException(404, "that question is no longer waiting for an answer")
    return {"ok": True}


@router.post("/questions/{question_id}/stash")
async def stash(question_id: str, agent: AgentRuntime = Agent) -> dict[str, Any]:
    """Put a question aside for later. It keeps waiting, out of the stack."""
    if not agent.stash_question(question_id):
        raise HTTPException(404, "that question is no longer waiting for an answer")
    return {"ok": True}


@router.post("/questions/{question_id}/unstash")
async def unstash(question_id: str, agent: AgentRuntime = Agent) -> dict[str, Any]:
    """Back to the needs-you stack."""
    return {"ok": bool(agent.device.unstash([question_id]))}
