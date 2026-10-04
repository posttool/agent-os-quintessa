from __future__ import annotations

import asyncio
import json
from importlib import resources

from quintessa.apps.installer import install_app, installed_app, uninstall_app
from quintessa.executors.common import call_capability
from quintessa.executors.step_context import StepContext
from quintessa.executors.step_outcome import StepOutcome
from quintessa.llm import schema as s
from quintessa.models import AppListing, Tool, ToolKind
from quintessa.serde import to_dict
from quintessa.tools.definitions import FUNCTION_SCHEMA, functions_from

_KINDS = [k.value for k in ToolKind if k not in (ToolKind.BUILTIN, ToolKind.APP)]
RESULTS_PER_QUERY = 8

SEARCH_SCHEMA = s.obj(
    {
        "reuse": s.array(s.string(), "Names of installed apps or tools that already fit."),
        "app_queries": s.array(s.string(), "1 to 3 app store searches; empty when nothing new is needed."),
        "uninstall": s.array(s.string(), "Names of agent-installed apps that are no longer useful."),
        "notes": s.string(),
    }
)

CHOOSE_SCHEMA = s.obj(
    {
        "install": s.array(s.obj({"app_id": s.string(), "reason": s.string()})),
        "tools": s.array(
            s.obj(
                {
                    "name": s.string(),
                    "description": s.string(),
                    "kind": s.enum_of(_KINDS),
                    "grounding": s.string("System prompt for llm tools; empty otherwise."),
                    "endpoint": s.string(),
                    "code": s.string(),
                    "functions": s.array(FUNCTION_SCHEMA),
                }
            ),
            "Tools to define yourself, only when no candidate app fits.",
        ),
        "notes": s.string(),
    }
)


def tool_suggestions() -> list[dict]:
    return json.loads(resources.files("quintessa.samples").joinpath("tool_suggestions.json").read_text())


class ToolDiscoveryExecutor:
    """Search the app store, install the apps that fit, and define a tool
    only when no app does. Installing never asks the user."""

    async def run(self, ctx: StepContext) -> StepOutcome:
        store = ctx.runtime.store
        first = await call_capability(ctx, SEARCH_SCHEMA)
        plan = first.data
        uninstalled = self._uninstall(ctx, plan["uninstall"])
        output: dict = {"reuse": plan["reuse"], "app_queries": plan["app_queries"], "uninstalled": uninstalled,
                        "candidates": [], "installed": [], "added": [], "notes": plan["notes"]}
        if not plan["app_queries"]:
            return StepOutcome(output, self._summary(output), first.model)

        candidates = await self._search(ctx, plan["app_queries"])
        output["candidates"] = [
            {**to_dict(c), "installed_as": t.name if (t := installed_app(store, c.app_id)) else None} for c in candidates
        ]
        second = await call_capability(
            ctx, CHOOSE_SCHEMA,
            {"app_queries": plan["app_queries"], "candidates": output["candidates"],
             "sample_tool_suggestions": tool_suggestions()},
            stage="choose",
        )
        choice = second.data
        by_id = {c.app_id: c for c in candidates}
        picks = [(by_id[i["app_id"]], i["reason"]) for i in choice["install"] if i["app_id"] in by_id]
        output["install_reasons"] = {listing.app_id: reason for listing, reason in picks}
        output["added"] = await self._define_tools(ctx, choice["tools"])
        output["notes"] = " ".join(n for n in (plan["notes"], choice["notes"]) if n)

        for listing, reason in picks:
            tool = await install_app(ctx.runtime, listing, need=f"{ctx.decision.focus} ({reason})")
            output["installed"].append(tool.name)
        return StepOutcome(output, self._summary(output), second.model)

    @staticmethod
    async def _search(ctx: StepContext, queries: list[str]) -> list[AppListing]:
        found = await asyncio.gather(*(ctx.runtime.apps.search(q, RESULTS_PER_QUERY) for q in queries[:3]))
        seen: dict[str, AppListing] = {}
        for listing in (listing for listings in found for listing in listings):
            seen.setdefault(listing.app_id, listing)
        return list(seen.values())

    @staticmethod
    def _uninstall(ctx: StepContext, names: list[str]) -> list[str]:
        store = ctx.runtime.store
        removed = []
        for name in names:
            tool = store.tools.get(name)
            if tool and tool.kind == ToolKind.APP and tool.created_by == "agent" and tool.listing:
                uninstall_app(store, tool.listing.app_id)
                removed.append(name)
        return removed

    @staticmethod
    async def _define_tools(ctx: StepContext, tools: list[dict]) -> list[str]:
        store = ctx.runtime.store
        added = []
        async with store.lock:
            for t in tools:
                existing = store.tools.get(t["name"])
                if existing and existing.kind in (ToolKind.BUILTIN, ToolKind.APP):
                    continue
                store.put_tool(
                    Tool(
                        name=t["name"],
                        description=t["description"],
                        kind=ToolKind(t["kind"]),
                        grounding=t["grounding"],
                        endpoint=t["endpoint"],
                        code=t["code"],
                        functions=functions_from(t["functions"]),
                    )
                )
                added.append(t["name"])
        return added

    @staticmethod
    def _summary(output: dict) -> str:
        parts = []
        if output["installed"]:
            parts.append(f"Installed {output['installed']}")
        if output["added"]:
            parts.append(f"Defined tools {output['added']}")
        if output["uninstalled"]:
            parts.append(f"Uninstalled {output['uninstalled']}")
        if output["reuse"]:
            parts.append(f"Reusing {output['reuse']}")
        if output["app_queries"] and not (output["installed"] or output["added"]):
            parts.append(f"Nothing installed for {output['app_queries']} ({len(output['candidates'])} candidates)")
        return ". ".join(parts + ([output["notes"]] if output["notes"] else [])) or "No tools needed"
