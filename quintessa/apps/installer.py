"""Installing an app turns a store listing into a tool the agent can call.

Play publishes no machine-readable list of what an app can do, so a model
writes the app's functions from its listing. A real binding (MCP, OpenAPI,
on-device App Functions) would replace that manifest with the one the
service reports, and set `binding` and `auth` from it."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from quintessa.llm import schema as s
from quintessa.memory import MemoryStore
from quintessa.models import AppListing, AuthKind, AuthRequirement, AuthState, Tool, ToolAuthor, ToolBinding, ToolKind
from quintessa.prompts import prompt
from quintessa.serde import to_dict
from quintessa.tools.definitions import FUNCTION_SCHEMA, functions_from

if TYPE_CHECKING:
    from quintessa.loop.runtime import AgentRuntime

MANIFEST_SCHEMA = s.obj(
    {
        "name": s.string("Short snake_case tool name for the app, such as opentable or uber_eats."),
        "description": s.string("One sentence on what the agent can do with this app."),
        "grounding": s.string("Extra facts for whoever plays this app's backend; empty if none."),
        "auth": s.enum_of(AuthKind, "The sign-in the real app needs for these functions."),
        "functions": s.array(FUNCTION_SCHEMA),
    }
)

MANIFEST_INSTRUCTIONS = prompt("app_manifest")

_SLUG = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    return _SLUG.sub("_", text.lower()).strip("_") or "app"


def installed_app(store: MemoryStore, app_id: str) -> Tool | None:
    return next((t for t in store.tools.values() if t.listing and t.listing.app_id == app_id), None)


def grounding_for(listing: AppListing, extra: str = "") -> str:
    by = f" by {listing.developer}" if listing.developer else ""
    text = prompt("app_grounding", title=listing.title, by=by, summary=listing.summary)
    return f"{text}\n{extra}" if extra else text


async def install_app(
    runtime: AgentRuntime, listing: AppListing, need: str = "", created_by: ToolAuthor = ToolAuthor.AGENT
) -> Tool:
    """Write the app's manifest and add it to the user's tools. Installing
    an app that is already installed returns the installed one."""
    store = runtime.store
    existing = installed_app(store, listing.app_id)
    if existing is not None:
        return existing
    result = await runtime.llm.generate_json(
        system=MANIFEST_INSTRUCTIONS,
        prompt=json.dumps({"listing": to_dict(listing), "user_need": need}, indent=1),
        schema=MANIFEST_SCHEMA,
        purpose=f"app_manifest:{listing.app_id}",
    )
    m = result.data
    async with store.lock:
        existing = installed_app(store, listing.app_id)  # another loop may have installed it meanwhile
        if existing is not None:
            return existing
        name = base = slug(m["name"] or listing.title)
        n = 2
        while name in store.tools:
            name, n = f"{base}_{n}", n + 1
        tool = Tool(
            name=name,
            description=m["description"] or listing.summary,
            kind=ToolKind.APP,
            functions=functions_from(m["functions"]),
            grounding=grounding_for(listing, m["grounding"]),
            created_by=created_by,
            listing=listing,
            binding=ToolBinding.SIMULATED,
            auth=AuthRequirement(AuthKind(m["auth"]), AuthState.SIMULATED),
        )
        store.put_tool(tool)
    return tool


def uninstall_app(store: MemoryStore, app_id: str) -> Tool | None:
    tool = installed_app(store, app_id)
    if tool is not None:
        store.delete_tool(tool.name)
    return tool
