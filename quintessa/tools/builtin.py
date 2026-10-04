"""The two default tools: web access and device control."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from quintessa.device import FOCUSED, FULL, BriefAction, BriefItem, DiscoveryItem
from quintessa.device.salience import Salience, clamp
from quintessa.models import Tool, ToolFunction, ToolKind, ToolParameter
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

BRIEF_CARD = (
    "A card is {text, topic_id, document_id, section_id, urgency, detail, action, expires_at, due_at, salience}; "
    "detail is one or two sentences shown when the card has no document; action is optional "
    "{tool, function, arguments: {name: value}, label} for a card the user can just say yes to; "
    'expires_at is an ISO time after which the card no longer applies ("leave by 3pm"), or omit it; '
    "due_at is the ISO time the thing the card is about happens (the meeting, the delivery), or omit it; "
    "salience is {urgency, relevance, affinity}, each 0 to 1: urgency is the personal risk if the user does "
    "not act (0.7-1 hard commitments like a meeting starting, a gate change, a courier outside; 0.3-0.7 "
    "perishable windows like rain in minutes, a 2FA code, a missed important call; 0-0.3 routine FYIs), "
    "relevance is how well it fits where the user is and what they are doing now, affinity is how much "
    "the person or business involved matters to the user. The brief is ordered by these"
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
            "Replace the whole contextual brief. To change a few cards, use update_brief.",
            [ToolParameter("items", "json array of cards. " + BRIEF_CARD)],
        ),
        ToolFunction(
            "update_brief",
            "Change cards in the contextual brief without rewriting it: put adds a card, or replaces "
            "the card with its id or its topic_id (a topic has one card); remove takes cards away "
            "that no longer hold. Use it when something new changes what a card says.",
            [
                ToolParameter(
                    "put", "json array of cards, each optionally with the id it replaces. " + BRIEF_CARD, required=False
                ),
                ToolParameter("remove", "json array of card ids to take away", required=False),
            ],
        ),
        ToolFunction(
            "show_document",
            "Bring a document into Spaces showing only what matters now: the sections to expand "
            '(at most 2; the rest fold into an outline) and a one-line reason. Use mode "full" when '
            "the user asks for the whole document. Omit sections to let the device pick.",
            [
                ToolParameter("document_id", "string"),
                ToolParameter("section_ids", "json array of section ids", required=False),
                ToolParameter("mode", '"focused" or "full"', required=False),
                ToolParameter("reason", "string", required=False),
            ],
        ),
        ToolFunction(
            "add_discovery",
            "Add a topic to the Discover screen.",
            [
                ToolParameter("title", "string"),
                ToolParameter("reason", "string"),
                ToolParameter("topic_id", "string", required=False),
            ],
        ),
        ToolFunction("notify", "Show a short notification.", [ToolParameter("text", "string")]),
    ],
)

BUILTIN_TOOLS = [WEB_TOOL, DEVICE_TOOL]


async def _search(args: dict[str, str], runtime: AgentRuntime) -> ToolCallResult:
    if runtime.search is None:
        return ToolCallResult("failed", "no web search backend is configured")
    return ToolCallResult("done", await runtime.search.search(args["query"]))


async def _fetch(args: dict[str, str], runtime: AgentRuntime) -> ToolCallResult:
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        response = await client.get(args["url"])
    text = response.text
    note = f"\n[truncated to {FETCH_LIMIT} of {len(text)} characters]" if len(text) > FETCH_LIMIT else ""
    return ToolCallResult("done" if response.is_success else "failed", text[:FETCH_LIMIT] + note)


async def _download(args: dict[str, str], runtime: AgentRuntime) -> ToolCallResult:
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


def _json_list(args: dict[str, str], name: str) -> tuple[list, str]:
    raw = args.get(name) or "[]"
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as e:
        return [], f"{name} is not JSON: {e}"
    if not isinstance(value, list):
        return [], f"{name} must be a JSON array"
    return value, ""


def _brief_cards(raw: list, runtime: AgentRuntime) -> tuple[list[BriefItem], list[str]]:
    """Cards from the agent's entries, one per topic: a later card for the
    same topic replaces the earlier one."""
    items: list[BriefItem] = []
    notes: list[str] = []
    for n, entry in enumerate(raw, 1):
        if not isinstance(entry, dict) or not entry.get("text"):
            notes.append(f"item {n}: skipped, it has no text")
            continue
        item, fixes = brief_item(entry, runtime)
        notes += [f"item {n}: {fix}" for fix in fixes]
        twin = next((i for i, b in enumerate(items) if item.topic_id and b.topic_id == item.topic_id), None)
        if twin is not None:
            notes.append(f"item {n}: replaces item {twin + 1}, a topic has one card")
            items.pop(twin)
        items.append(item)
    return items, notes


async def _set_brief(args: dict[str, str], runtime: AgentRuntime) -> ToolCallResult:
    raw, problem = _json_list(args, "items")
    if problem:
        return ToolCallResult("failed", problem)
    items, notes = _brief_cards(raw, runtime)
    runtime.device.set_brief(items)
    return ToolCallResult("done", "; ".join([f"brief shows {len(items)} items", *notes]))


async def _update_brief(args: dict[str, str], runtime: AgentRuntime) -> ToolCallResult:
    put, problem = _json_list(args, "put")
    remove, problem2 = _json_list(args, "remove")
    if problem or problem2:
        return ToolCallResult("failed", problem or problem2)
    items, notes = _brief_cards(put, runtime)
    lines: list[str] = []
    gone = runtime.device.remove_brief([str(i) for i in remove])
    lines += [f"removed {b.id} ({b.text})" for b in gone]
    known = {b.id for b in gone}
    lines += [f"no card {i} to remove" for i in remove if str(i) not in known]
    for item in items:
        replaced = runtime.device.put_brief(item)
        lines.append(
            f"replaced {item.id} ({replaced.text} -> {item.text})" if replaced else f"added {item.id} ({item.text})"
        )
    lines.append(f"brief shows {len(runtime.device.state.brief)} items")
    return ToolCallResult("done", "; ".join([*lines, *notes]))


def brief_item(entry: dict, runtime: AgentRuntime) -> tuple[BriefItem, list[str]]:
    """Build a brief card, keeping only links that lead somewhere: a topic and
    document that exist, a section of that document, an installed tool. What
    was dropped is reported back so the agent can learn from it."""
    store = runtime.store
    fixes: list[str] = []
    topic_id = entry.get("topic_id") or None
    topic = store.topics.get(topic_id) if topic_id else None
    if topic_id and topic is None:
        fixes.append(f"no topic {topic_id}, dropped the link")
        topic_id = None
    document_id = entry.get("document_id") or None
    if document_id is None and topic is not None and topic.document_id:
        document_id = topic.document_id
    doc = store.documents.get(document_id) if document_id else None
    if document_id and (doc is None or doc.status.value == "archived"):
        fixes.append(f"no open document {document_id}, kept as a card")
        document_id, doc = None, None
    section_id = entry.get("section_id") or None
    if section_id and (doc is None or doc.section(section_id) is None):
        fixes.append(f"no section {section_id} in {document_id or 'a document'}, dropped it")
        section_id = None
    action, problem = brief_action(entry.get("action"), runtime)
    if problem:
        fixes.append(f"action dropped: {problem}")
    expires_at, problem = parse_time(entry.get("expires_at"))
    if problem:
        fixes.append(f"expires_at dropped: {problem}")
    due_at, problem = parse_time(entry.get("due_at"))
    if problem:
        fixes.append(f"due_at dropped: {problem}")
    raw_salience = entry.get("salience") if isinstance(entry.get("salience"), dict) else {}
    scores = Salience(
        urgency=clamp(raw_salience["urgency"], 0.4) if raw_salience.get("urgency") is not None else None,
        relevance=clamp(raw_salience.get("relevance"), 0.5),
        affinity=clamp(raw_salience.get("affinity"), 0.5),
    )
    item = BriefItem(
        str(entry["text"]),
        topic_id,
        document_id,
        section_id,
        urgency=entry.get("urgency") or "normal",
        detail=str(entry.get("detail") or ""),
        action=action,
        expires_at=expires_at,
        due_at=due_at,
        salience=scores,
    )
    if entry.get("id"):
        item.id = str(entry["id"])
    return item, fixes


def parse_time(raw: object) -> tuple[datetime | None, str]:
    """An ISO time; one without a zone is taken as UTC."""
    if not raw:
        return None, ""
    try:
        at = datetime.fromisoformat(str(raw))
    except ValueError:
        return None, f"{raw!r} is not an ISO time"
    return (at if at.tzinfo else at.replace(tzinfo=UTC)), ""


def brief_action(raw: object, runtime: AgentRuntime) -> tuple[BriefAction | None, str]:
    if not raw:
        return None, ""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None, "it is not an object"
    if not isinstance(raw, dict):
        return None, "it is not an object"
    tool = runtime.store.tools.get(str(raw.get("tool") or ""))
    if tool is None:
        return None, f"{raw.get('tool')!r} is not installed"
    function = tool.function(str(raw.get("function") or ""))
    if function is None:
        return None, f"{tool.name} has no function {raw.get('function')!r}"
    arguments = raw.get("arguments") or {}
    if isinstance(arguments, list):  # [{name, value}], the tool_use shape
        arguments = {a.get("name"): a.get("value") for a in arguments if isinstance(a, dict)}
    if not isinstance(arguments, dict):
        return None, "arguments must be an object"
    arguments = {str(k): v if isinstance(v, str) else json.dumps(v) for k, v in arguments.items() if k}
    label = str(raw.get("label") or function.name.replace("_", " ").capitalize())
    return BriefAction(tool.name, function.name, label, arguments), ""


async def _show_document(args: dict[str, str], runtime: AgentRuntime) -> ToolCallResult:
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


async def _add_discovery(args: dict[str, str], runtime: AgentRuntime) -> ToolCallResult:
    runtime.device.add_discovery(DiscoveryItem(args["title"], args["reason"], args.get("topic_id") or None))
    return ToolCallResult("done", f"added {args['title']} to Discover")


async def _notify(args: dict[str, str], runtime: AgentRuntime) -> ToolCallResult:
    runtime.device.notify(args["text"])
    return ToolCallResult("done", "notified")


BUILTIN_IMPLEMENTATIONS: dict[tuple[str, str], Impl] = {
    ("web", "search"): _search,
    ("web", "fetch"): _fetch,
    ("web", "download"): _download,
    ("device", "set_brief"): _set_brief,
    ("device", "update_brief"): _update_brief,
    ("device", "show_document"): _show_document,
    ("device", "add_discovery"): _add_discovery,
    ("device", "notify"): _notify,
}
