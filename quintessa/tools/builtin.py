"""The two default tools: web access and device control."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Awaitable, Callable

import httpx

from quintessa.device import FOCUSED, FULL, BriefItem, DiscoveryItem
from quintessa.models import OversightLevel, Tool, ToolFunction, ToolKind, ToolParameter
from quintessa.tools.tool_call_result import ToolCallResult

if TYPE_CHECKING:
    from quintessa.loop.runtime import AgentRuntime

Impl = Callable[[dict[str, str], "AgentRuntime"], Awaitable[ToolCallResult]]

FETCH_LIMIT = 20_000

WEB_TOOL = Tool(
    name="web",
    description="Web access: Google search, reading pages, downloading files to the device.",
    kind=ToolKind.BUILTIN,
    created_by="system",
    functions=[
        ToolFunction("search", "Search the web.", [ToolParameter("query", "string")]),
        ToolFunction("fetch", "Read a web page as text.", [ToolParameter("url", "string")]),
        ToolFunction("download", "Download a file to the device.", [ToolParameter("url", "string")]),
    ],
)

DEVICE_TOOL = Tool(
    name="device",
    description=(
        "Device control: update the experience surfaces. The contextual brief is a short "
        "ranked list of glanceable calls to action; Spaces shows documents; Discover shows "
        "related topics the user did not ask for."
    ),
    kind=ToolKind.BUILTIN,
    created_by="system",
    functions=[
        ToolFunction(
            "set_brief",
            "Replace the contextual brief.",
            [ToolParameter("items", "json array of {text, topic_id, document_id, section_id, urgency}")],
        ),
        ToolFunction(
            "show_document",
            "Bring a document into Spaces showing only what matters now: the sections to expand "
            "(at most 2; the rest fold into an outline) and a one-line reason. Use mode \"full\" when "
            "the user asks for the whole document. Omit sections to let the device pick.",
            [
                ToolParameter("document_id", "string"),
                ToolParameter("section_ids", "json array of section ids", required=False),
                ToolParameter("mode", "\"focused\" or \"full\"", required=False),
                ToolParameter("reason", "string", required=False),
            ],
        ),
        ToolFunction(
            "add_discovery",
            "Add a topic to the Discover screen.",
            [ToolParameter("title", "string"), ToolParameter("reason", "string"),
             ToolParameter("topic_id", "string", required=False)],
        ),
        ToolFunction("notify", "Show a short notification.", [ToolParameter("text", "string")]),
    ],
)

BUILTIN_TOOLS = [WEB_TOOL, DEVICE_TOOL]


async def _search(args: dict[str, str], runtime: "AgentRuntime") -> ToolCallResult:
    if runtime.search is None:
        return ToolCallResult("failed", "no web search backend is configured")
    return ToolCallResult("done", await runtime.search.search(args["query"]))


async def _fetch(args: dict[str, str], runtime: "AgentRuntime") -> ToolCallResult:
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        response = await client.get(args["url"])
    text = response.text
    note = f"\n[truncated to {FETCH_LIMIT} of {len(text)} characters]" if len(text) > FETCH_LIMIT else ""
    return ToolCallResult("done" if response.is_success else "failed", text[:FETCH_LIMIT] + note)


async def _download(args: dict[str, str], runtime: "AgentRuntime") -> ToolCallResult:
    from quintessa.state import user_folder_name  # quintessa.state imports the runtime's models

    folder = Path(runtime.data_dir) / "downloads" / user_folder_name(runtime.user_id)
    folder.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
        response = await client.get(args["url"])
    if not response.is_success:
        return ToolCallResult("failed", f"HTTP {response.status_code}")
    target = folder / (Path(httpx.URL(args["url"]).path).name or "download")
    target.write_bytes(response.content)
    return ToolCallResult("done", f"saved {len(response.content)} bytes to {target}")


async def _set_brief(args: dict[str, str], runtime: "AgentRuntime") -> ToolCallResult:
    items = json.loads(args["items"])
    runtime.device.set_brief(
        [
            BriefItem(i["text"], i.get("topic_id"), i.get("document_id"), i.get("section_id"), urgency=i.get("urgency", "normal"))
            for i in items
        ]
    )
    return ToolCallResult("done", f"brief shows {len(items)} items")


async def _show_document(args: dict[str, str], runtime: "AgentRuntime") -> ToolCallResult:
    doc = runtime.store.documents.get(args["document_id"])
    if doc is None:
        return ToolCallResult("failed", f"no document {args['document_id']}")
    mode = args.get("mode") or FOCUSED
    if mode not in (FOCUSED, FULL):
        return ToolCallResult("failed", f"mode must be {FOCUSED!r} or {FULL!r}")
    raw = args.get("section_ids") or "[]"
    try:
        section_ids = json.loads(raw)
    except json.JSONDecodeError:
        section_ids = [raw]
    if isinstance(section_ids, str):
        section_ids = [section_ids]
    unknown = [sid for sid in section_ids if doc.section(sid) is None]
    if unknown:
        return ToolCallResult("failed", f"{doc.id} has no sections {unknown}; it has {[s.id for s in doc.sections]}")
    runtime.device.show_document(doc.id, section_ids, mode, args.get("reason") or "")
    shown = "the whole document" if mode == FULL else (", ".join(section_ids) or "what matters now")
    return ToolCallResult("done", f"showing {doc.id}: {shown}")


async def _add_discovery(args: dict[str, str], runtime: "AgentRuntime") -> ToolCallResult:
    runtime.device.add_discovery(DiscoveryItem(args["title"], args["reason"], args.get("topic_id") or None))
    return ToolCallResult("done", f"added {args['title']} to Discover")


async def _notify(args: dict[str, str], runtime: "AgentRuntime") -> ToolCallResult:
    runtime.device.notify(args["text"])
    return ToolCallResult("done", "notified")


BUILTIN_IMPLEMENTATIONS: dict[tuple[str, str], Impl] = {
    ("web", "search"): _search,
    ("web", "fetch"): _fetch,
    ("web", "download"): _download,
    ("device", "set_brief"): _set_brief,
    ("device", "show_document"): _show_document,
    ("device", "add_discovery"): _add_discovery,
    ("device", "notify"): _notify,
}

# Device changes are the agent's own surface; nothing here needs approval.
assert all(f.oversight == OversightLevel.AUTO for t in BUILTIN_TOOLS for f in t.functions)
