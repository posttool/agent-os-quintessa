from __future__ import annotations

from quintessa.clock import now
from quintessa.executors.common import call_capability
from quintessa.executors.generative_ui_executor import CONFIRM_YES, record_permission
from quintessa.executors.step_context import StepContext
from quintessa.executors.step_outcome import StepOutcome
from quintessa.llm import schema as s
from quintessa.models import (
    OversightLevel,
    Subscription,
    Tool,
    ToolFunction,
    UXField,
    UXFieldKind,
    UXPurpose,
    UXRequest,
    UXResponse,
)
from quintessa.serde import to_dict
from quintessa.tools.runner import run_tool


def schema_for(tool_names: list[str]) -> dict:
    return s.obj(
        {
            "tool": s.enum_of(tool_names),
            "function": s.string(),
            "arguments": s.array(s.obj({"name": s.string(), "value": s.string()})),
            "rationale": s.string(),
            "document_id": s.nullable(s.string()),
            "section_id": s.nullable(s.string()),
            "track_progress": s.boolean(),
            "progress_stages": s.array(s.string()),
            "permission_prompt": s.string("Question to ask if this call needs the user's approval."),
        }
    )


def needs_permission(ctx: StepContext, tool: Tool, function: ToolFunction) -> bool | None:
    """True: ask first. False: go ahead. None: the user already declined in this chain."""
    session_grants = [p for p in ctx.session.permissions if p.tool == tool.name and p.function == function.name]
    if session_grants:
        return None if not session_grants[-1].granted else False
    if function.oversight in (OversightLevel.AUTO, OversightLevel.AUTO_FROM_MEMORY):
        return False
    if function.oversight == OversightLevel.CONFIRM_ONCE and ctx.runtime.store.persistent_grant(tool.name, function.name):
        return False
    return True


class ToolUseExecutor:
    async def run(self, ctx: StepContext) -> StepOutcome:
        store = ctx.runtime.store
        result = await call_capability(ctx, schema_for(sorted(store.tools)))
        call = result.data
        tool = store.tools[call["tool"]]
        function = tool.function(call["function"])
        if function is None:
            return StepOutcome(call, f"{tool.name} has no function {call['function']}", result.model)
        args = {a["name"]: a["value"] for a in call["arguments"]}

        async def execute() -> StepOutcome:
            outcome = await run_tool(ctx.runtime, tool, function, args, purpose=call["rationale"])
            output = {**call, "result": to_dict(outcome)}
            stages = outcome.progress_stages or call["progress_stages"]
            if (call["track_progress"] or function.long_running or outcome.status == "in_progress") and stages:
                subscription = Subscription(
                    tool=tool.name,
                    function=function.name,
                    description=f"{tool.name}.{function.name}: {call['rationale']}",
                    stages=stages,
                    document_id=call["document_id"],
                    section_id=call["section_id"],
                )
                store.put_subscription(subscription)
                ctx.runtime.ambient.follow(subscription)
                output["subscription_id"] = subscription.id
            self._note_action(ctx, call, f"{tool.name}.{function.name}: {outcome.status} - {outcome.result}")
            return StepOutcome(output, f"{tool.name}.{function.name} -> {outcome.status}: {outcome.result}", result.model)

        gate = needs_permission(ctx, tool, function)
        if gate is None:
            return StepOutcome(call, f"Skipped {tool.name}.{function.name}: the user declined it earlier", result.model)
        if gate is False:
            return await execute()

        request = UXRequest(
            session_id=ctx.session.id,
            purpose=UXPurpose.PERMISSION,
            prompt=call["permission_prompt"] or f"Allow {tool.name} to {function.name}?",
            fields=[UXField("approve", UXFieldKind.CONFIRM, "Approve", [CONFIRM_YES, "no"])],
            document_id=call["document_id"],
            section_id=call["section_id"],
            tool=tool.name,
            function=function.name,
        )

        async def on_answer(response: UXResponse) -> StepOutcome:
            permission = record_permission(ctx, request, response)
            if permission and permission.granted:
                return await execute()
            return StepOutcome({**call, "permission": "declined"}, f"User declined {tool.name}.{function.name}", result.model)

        return StepOutcome(call, f"Asking permission for {tool.name}.{function.name}", result.model, request, on_answer)

    @staticmethod
    def _note_action(ctx: StepContext, call: dict, line: str) -> None:
        if call["tool"] == "device":  # changing what the user sees is not progress on the section
            return
        doc = ctx.runtime.store.documents.get(call["document_id"] or "")
        section = doc.section(call["section_id"]) if doc and call["section_id"] else None
        if section is not None:
            section.actions_taken.append(line)
            section.updated_at = now()
            ctx.runtime.store.upsert_document(doc)
