"""The two default tools: web access and device control."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from quintessa.device import FOCUSED, FULL, DiscoveryItem
from quintessa.device.cards import cards_from_entries
from quintessa.models import Tool, ToolAuthor, ToolCallStatus, ToolFunction, ToolKind, ToolParameter
from quintessa.paths import user_folder_name
from quintessa.tools.tool_call_result import ToolCallResult

if TYPE_CHECKING:
    from quintessa.loop.runtime import AgentRuntime

Impl = Callable[[dict[str, str], "AgentRuntime"], Awaitable[ToolCallResult]]

FETCH_LIMIT = 20_000


def clip(text: str) -> str:
    """A response body cut to FETCH_LIMIT characters, saying so when cut."""
    if len(text) <= FETCH_LIMIT:
        return text
    return f"{text[:FETCH_LIMIT]}\n[truncated to {FETCH_LIMIT} of {len(text)} characters]"


WEB_TOOL = Tool(
    name="web",
    description="Web access: Google search, reading pages, downloading files to the device.",
    kind=ToolKind.BUILTIN,
    created_by=ToolAuthor.SYSTEM,
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
    created_by=ToolAuthor.SYSTEM,
    functions=[
        ToolFunction(
            "set_brief",
            "Replace the whole contextual brief. To change a few cards, use update_brief.",
            [ToolParameter("cards", "json array of cards. " + BRIEF_CARD)],
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
        return ToolCallResult(ToolCallStatus.FAILED, "no web search backend is configured")
    return ToolCallResult(ToolCallStatus.DONE, await runtime.search.search(args["query"]))


async def _fetch(args: dict[str, str], runtime: AgentRuntime) -> ToolCallResult:
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        response = await client.get(args["url"])
    status = ToolCallStatus.DONE if response.is_success else ToolCallStatus.FAILED
    return ToolCallResult(status, clip(response.text))


async def _download(args: dict[str, str], runtime: AgentRuntime) -> ToolCallResult:
    folder = Path(runtime.data_dir) / "downloads" / user_folder_name(runtime.user_id)
    folder.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
        response = await client.get(args["url"])
    if not response.is_success:
        return ToolCallResult(ToolCallStatus.FAILED, f"HTTP {response.status_code}")
    target = folder / (Path(httpx.URL(args["url"]).path).name or "download")
    target.write_bytes(response.content)
    return ToolCallResult(ToolCallStatus.DONE, f"saved {len(response.content)} bytes to {target}")


def _json_list(args: dict[str, str], name: str) -> tuple[list, str]:
    raw = args.get(name) or "[]"
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as e:
        return [], f"{name} is not JSON: {e}"
    if not isinstance(value, list):
        return [], f"{name} must be a JSON array"
    return value, ""


async def _set_brief(args: dict[str, str], runtime: AgentRuntime) -> ToolCallResult:
    raw, problem = _json_list(args, "cards")
    if problem:
        return ToolCallResult(ToolCallStatus.FAILED, problem)
    cards, notes = cards_from_entries(raw, runtime.store)
    runtime.device.set_brief(cards)
    return ToolCallResult(ToolCallStatus.DONE, "; ".join([f"brief shows {len(cards)} cards", *notes]))


async def _update_brief(args: dict[str, str], runtime: AgentRuntime) -> ToolCallResult:
    put, problem = _json_list(args, "put")
    remove, problem2 = _json_list(args, "remove")
    if problem or problem2:
        return ToolCallResult(ToolCallStatus.FAILED, problem or problem2)
    cards, notes = cards_from_entries(put, runtime.store)
    lines: list[str] = []
    gone = runtime.device.remove_cards([str(i) for i in remove])
    lines += [f"removed {b.id} ({b.text})" for b in gone]
    known = {b.id for b in gone}
    lines += [f"no card {i} to remove" for i in remove if str(i) not in known]
    for card in cards:
        replaced = runtime.device.put_brief(card)
        lines.append(
            f"replaced {card.id} ({replaced.text} -> {card.text})" if replaced else f"added {card.id} ({card.text})"
        )
    lines.append(f"brief shows {len(runtime.device.state.brief)} cards")
    return ToolCallResult(ToolCallStatus.DONE, "; ".join([*lines, *notes]))


async def _show_document(args: dict[str, str], runtime: AgentRuntime) -> ToolCallResult:
    doc = runtime.store.documents.get(args["document_id"])
    if doc is None:
        return ToolCallResult(ToolCallStatus.FAILED, f"no document {args['document_id']}")
    mode = args.get("mode") or FOCUSED
    if mode not in (FOCUSED, FULL):
        return ToolCallResult(ToolCallStatus.FAILED, f"mode must be {FOCUSED!r} or {FULL!r}")
    raw = args.get("section_ids") or "[]"
    try:
        section_ids = json.loads(raw)
    except json.JSONDecodeError:
        section_ids = [raw]
    if isinstance(section_ids, str):
        section_ids = [section_ids]
    unknown = [sid for sid in section_ids if doc.section(sid) is None]
    if unknown:
        return ToolCallResult(
            ToolCallStatus.FAILED, f"{doc.id} has no sections {unknown}; it has {[s.id for s in doc.sections]}"
        )
    runtime.device.show_document(doc.id, section_ids, mode, args.get("reason") or "")
    shown = "the whole document" if mode == FULL else (", ".join(section_ids) or "what matters now")
    return ToolCallResult(ToolCallStatus.DONE, f"showing {doc.id}: {shown}")


async def _add_discovery(args: dict[str, str], runtime: AgentRuntime) -> ToolCallResult:
    runtime.device.add_discovery(DiscoveryItem(args["title"], args["reason"], args.get("topic_id") or None))
    return ToolCallResult(ToolCallStatus.DONE, f"added {args['title']} to Discover")


async def _notify(args: dict[str, str], runtime: AgentRuntime) -> ToolCallResult:
    runtime.device.notify(args["text"])
    return ToolCallResult(ToolCallStatus.DONE, "notified")


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
