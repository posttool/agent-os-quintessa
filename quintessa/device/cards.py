"""Cards built from what the agent writes, keeping only links that lead
somewhere. The device tool and the end-of-session brief refresh both use
these."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from quintessa.clock import parse_time
from quintessa.device.card import Card, CardAction
from quintessa.device.salience import Salience, clamp

if TYPE_CHECKING:
    from quintessa.memory import MemoryStore


def cards_from_entries(raw: list, store: MemoryStore) -> tuple[list[Card], list[str]]:
    """Cards from the agent's entries, one per topic: a later card for the
    same topic replaces the earlier one."""
    cards: list[Card] = []
    notes: list[str] = []
    for n, entry in enumerate(raw, 1):
        if not isinstance(entry, dict) or not entry.get("text"):
            notes.append(f"card {n}: skipped, it has no text")
            continue
        card, fixes = build_card(entry, store)
        notes += [f"card {n}: {fix}" for fix in fixes]
        twin = next((i for i, b in enumerate(cards) if card.topic_id and b.topic_id == card.topic_id), None)
        if twin is not None:
            notes.append(f"card {n}: replaces card {twin + 1}, a topic has one card")
            cards.pop(twin)
        cards.append(card)
    return cards, notes


def build_card(entry: dict, store: MemoryStore) -> tuple[Card, list[str]]:
    """Build a brief card, keeping only links that lead somewhere: a topic and
    document that exist, a section of that document, an installed tool. What
    was dropped is reported back so the agent can learn from it."""
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
    if document_id and (doc is None or doc.archived):
        fixes.append(f"no open document {document_id}, kept as a card")
        document_id, doc = None, None
    section_id = entry.get("section_id") or None
    if section_id and (doc is None or doc.section(section_id) is None):
        fixes.append(f"no section {section_id} in {document_id or 'a document'}, dropped it")
        section_id = None
    action, problem = card_action(entry.get("action"), store)
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
    card = Card(
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
        card.id = str(entry["id"])
    return card, fixes


def card_action(raw: object, store: MemoryStore) -> tuple[CardAction | None, str]:
    """A one-tap action, kept only when it names an installed tool function."""
    if not raw:
        return None, ""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None, "it is not an object"
    if not isinstance(raw, dict):
        return None, "it is not an object"
    tool = store.tools.get(str(raw.get("tool") or ""))
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
    return CardAction(tool.name, function.name, label, arguments), ""
