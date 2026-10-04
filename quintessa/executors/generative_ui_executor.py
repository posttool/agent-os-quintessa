from __future__ import annotations

from typing import TYPE_CHECKING

from quintessa.executors.common import call_capability
from quintessa.executors.step_context import StepContext
from quintessa.executors.step_outcome import StepOutcome
from quintessa.llm import schema as s
from quintessa.models import (
    OversightLevel,
    Permission,
    UXField,
    UXFieldKind,
    UXPurpose,
    UXRequest,
    UXResponse,
)
from quintessa.models.ux_response import WITHDRAWN
from quintessa.serde import to_dict

if TYPE_CHECKING:
    from quintessa.memory.store import MemoryStore

# Skins send this value for an approved `confirm` field.
CONFIRM_YES = "yes"

SCHEMA = s.obj(
    {
        "prompt": s.string("The question, in a few words."),
        "context": s.string("One short sentence on why you are asking, shown under the question."),
        "purpose": s.enum_of(UXPurpose),
        "fields": s.array(
            s.obj(
                {
                    "name": s.string(),
                    "kind": s.enum_of(UXFieldKind),
                    "label": s.string(),
                    "options": s.array(s.string()),
                }
            )
        ),
        "document_id": s.nullable(s.string()),
        "section_id": s.nullable(s.string()),
        "topic_id": s.nullable(s.string("Topic this question is about, when there is one.")),
        "tool": s.nullable(s.string("Tool whose function this permission authorizes.")),
        "function": s.nullable(s.string()),
    }
)


def question_topic(store: MemoryStore, topic_id: str | None, document_id: str | None) -> str | None:
    """The topic a question belongs to: the one named if it exists, else the
    topic of its document."""
    if topic_id and topic_id in store.topics:
        return topic_id
    doc = store.documents.get(document_id) if document_id else None
    return doc.topic_id if doc is not None else None


def build_request(session_id: str, data: dict, store: MemoryStore) -> UXRequest:
    return UXRequest(
        session_id=session_id,
        purpose=UXPurpose(data["purpose"]),
        prompt=data["prompt"],
        fields=[UXField(f["name"], UXFieldKind(f["kind"]), f["label"], f["options"]) for f in data["fields"]],
        document_id=data["document_id"],
        section_id=data["section_id"],
        tool=data["tool"],
        function=data["function"],
        topic_id=question_topic(store, data.get("topic_id"), data["document_id"]),
        context=data.get("context") or "",
    )


def is_approval(request: UXRequest, response: UXResponse) -> bool:
    if response.dismissed:
        return False
    confirms = [f.name for f in request.fields if f.kind == UXFieldKind.CONFIRM]
    return bool(confirms) and all(response.values.get(name) == CONFIRM_YES for name in confirms)


def record_permission(ctx: StepContext, request: UXRequest, response: UXResponse) -> Permission | None:
    """A permission answer carries forward through this chain, and is kept in
    memory when the function only needs confirming once."""
    if request.purpose != UXPurpose.PERMISSION or not request.tool or not request.function:
        return None
    granted = is_approval(request, response)
    permission = Permission(
        tool=request.tool,
        function=request.function,
        granted=granted,
        scope="session",
        detail=request.prompt,
        session_id=ctx.session.id,
        ux_request_id=request.id,
    )
    ctx.session.permissions.append(permission)
    tool = ctx.runtime.store.tools.get(request.tool)
    function = tool.function(request.function) if tool else None
    if granted and function and function.oversight == OversightLevel.CONFIRM_ONCE:
        ctx.runtime.store.add_permission(
            Permission(request.tool, request.function, True, "persistent", request.prompt, ctx.session.id, request.id)
        )
    return permission


class GenerativeUIExecutor:
    async def run(self, ctx: StepContext) -> StepOutcome:
        result = await call_capability(ctx, SCHEMA)
        request = build_request(ctx.session.id, result.data, ctx.runtime.store)

        async def on_answer(response: UXResponse) -> StepOutcome:
            permission = record_permission(ctx, request, response)
            answer = "dismissed" if response.dismissed else response.values
            summary = f"Asked '{request.prompt}'; user answered {answer}"
            if response.surface_context.startswith(WITHDRAWN):
                reason = response.surface_context[len(WITHDRAWN) :]
                summary = f"Asked '{request.prompt}', then withdrew it before the user answered ({reason})"
            if permission:
                summary += f"; {request.tool}.{request.function} {'granted' if permission.granted else 'declined'}"
            return StepOutcome(
                output={"request": to_dict(request), "response": to_dict(response)},
                summary=summary,
                model=result.model,
            )

        return StepOutcome(
            output={"request": to_dict(request)},
            summary=f"Asked '{request.prompt}'",
            model=result.model,
            pending_ux=request,
            on_answer=on_answer,
        )
