from __future__ import annotations

from quintessa.executors.common import call_capability
from quintessa.executors.step_context import StepContext
from quintessa.executors.step_outcome import StepOutcome
from quintessa.llm import schema as s
from quintessa.memory.apply import OPERATIONS, apply_operations
from quintessa.models import DocumentStatus, EdgeType, NodeType, TriggerType

_NODE = s.obj(
    {
        "type": s.enum_of(NodeType),
        "title": s.string(),
        "body": s.string(),
        "topic_id": s.nullable(s.string()),
    }
)
_EDGE = s.obj({"source_id": s.string(), "target_id": s.string(), "type": s.enum_of(EdgeType), "note": s.string()})
_TOPIC = s.obj(
    {
        "title": s.string(),
        "category": s.string(),
        "parent_id": s.nullable(s.string()),
        "summary": s.string(),
        "new_info": s.string("What changed since the user last saw this topic; empty if nothing."),
        "importance": s.string(),
        "progress": s.number("0 to 1"),
        "progress_note": s.string(),
        "due": s.string("A date, or a relative phrase like 'before Mom arrives'; empty if none."),
        "triggers": s.array(s.obj({"type": s.enum_of(TriggerType), "condition": s.string(), "reasoning": s.string()})),
        "document_id": s.nullable(s.string()),
    }
)
_DOCUMENT = s.obj(
    {
        "title": s.string(),
        "topic_id": s.nullable(s.string()),
        "description": s.string(),
        "status": s.enum_of(DocumentStatus),
        "progress_overview": s.string(),
        "links": s.array(s.string()),
        "key_dates": s.array(s.obj({"when": s.string(), "label": s.string(), "tentative": s.boolean()})),
        "observations": s.array(s.string()),
    }
)
_SECTION = s.obj(
    {
        "document_id": s.string(),
        "title": s.string(),
        "overview": s.string(),
        "status": s.string(),
        "details": s.string(),
        "actions_taken": s.array(s.string()),
        "suggested_actions": s.array(s.string()),
    }
)

SCHEMA = s.obj(
    {
        "summary": s.string("What you changed, and any facts retrieved that matter for the focus."),
        "operations": s.array(
            s.obj(
                {
                    "op": s.enum_of(OPERATIONS),
                    "id": s.string("Id of the node, topic, document or section."),
                    "reason": s.string(),
                    "node": s.nullable(_NODE),
                    "edge": s.nullable(_EDGE),
                    "topic": s.nullable(_TOPIC),
                    "document": s.nullable(_DOCUMENT),
                    "section": s.nullable(_SECTION),
                }
            )
        ),
    }
)


class MemoryExecutor:
    async def run(self, ctx: StepContext) -> StepOutcome:
        result = await call_capability(ctx, SCHEMA)
        store = ctx.runtime.store
        async with store.lock:
            applied = apply_operations(store, result.data["operations"], ctx.session.trigger.id)
        summary = result.data["summary"]
        skipped = [line for line in applied if line.startswith("skipped")]
        if skipped:
            summary += "\n\nNot applied: " + "; ".join(skipped)
        return StepOutcome(
            output={**result.data, "applied": applied},
            summary=summary,
            model=result.model,
        )
