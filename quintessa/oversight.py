"""Oversight: whether a tool call may run now, how an approval question is
read, and what a granted or declined permission leaves behind."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from quintessa.models import (
    Answer,
    FieldKind,
    OversightLevel,
    Permission,
    PermissionScope,
    Question,
    QuestionPurpose,
    ReasoningSession,
    Tool,
    ToolFunction,
)

if TYPE_CHECKING:
    from quintessa.memory.store import MemoryStore

# Skins send this value for an approved `confirm` field.
CONFIRM_YES = "yes"


class Gate(Enum):
    """What may happen with a tool call now."""

    GO = "go"  # run it
    ASK = "ask"  # ask the user first
    DECLINED = "declined"  # the user already said no in this session


def gate(session: ReasoningSession, store: MemoryStore, tool: Tool, function: ToolFunction) -> Gate:
    """A grant or refusal earlier in this session decides first, then the
    function's oversight level, then a confirm_once grant kept in memory."""
    session_grants = [p for p in session.permissions if p.tool == tool.name and p.function == function.name]
    if session_grants:
        return Gate.GO if session_grants[-1].granted else Gate.DECLINED
    if function.oversight in (OversightLevel.AUTO, OversightLevel.AUTO_FROM_MEMORY):
        return Gate.GO
    if function.oversight == OversightLevel.CONFIRM_ONCE and store.persistent_grant(tool.name, function.name):
        return Gate.GO
    return Gate.ASK


def is_approval(question: Question, answer: Answer) -> bool:
    """Every confirm field of the question was answered yes."""
    if answer.dismissed:
        return False
    confirms = [f.name for f in question.fields if f.kind == FieldKind.CONFIRM]
    return bool(confirms) and all(answer.values.get(name) == CONFIRM_YES for name in confirms)


def record_permission(
    session: ReasoningSession, store: MemoryStore, question: Question, answer: Answer
) -> Permission | None:
    """A permission answer carries forward through this session, and is kept in
    memory when the function only needs confirming once."""
    if question.purpose != QuestionPurpose.PERMISSION or not question.tool or not question.function:
        return None
    granted = is_approval(question, answer)
    permission = Permission(
        tool=question.tool,
        function=question.function,
        granted=granted,
        scope=PermissionScope.SESSION,
        detail=question.prompt,
        session_id=session.id,
        question_id=question.id,
    )
    session.permissions.append(permission)
    tool = store.tools.get(question.tool)
    function = tool.function(question.function) if tool else None
    if granted and function and function.oversight == OversightLevel.CONFIRM_ONCE:
        store.add_permission(
            Permission(
                question.tool,
                question.function,
                True,
                PermissionScope.PERSISTENT,
                question.prompt,
                session.id,
                question.id,
            )
        )
    return permission
