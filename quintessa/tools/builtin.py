"""The two default tools: web access and device control."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import yaml

from quintessa.device import FOCUSED, FULL, DiscoveryItem
from quintessa.device.cards import cards_from_entries
from quintessa.models import Tool, ToolAuthor, ToolCallStatus, ToolKind
from quintessa.paths import user_folder_name
from quintessa.prompts import prompt
from quintessa.serde import from_dict
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


BRIEF_CARD = prompt("card_format")


def _load_builtin_tools() -> list[Tool]:
    entries = yaml.safe_load(resources.files("quintessa.tools").joinpath("builtin_tools.yaml").read_text())
    tools = [from_dict(Tool, {**e, "kind": ToolKind.BUILTIN, "created_by": ToolAuthor.SYSTEM}) for e in entries]
    for parameter in (p for tool in tools for f in tool.functions for p in f.parameters):
        parameter.type = parameter.type.replace("{card_format}", BRIEF_CARD)
    return tools


WEB_TOOL, DEVICE_TOOL = _load_builtin_tools()
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
