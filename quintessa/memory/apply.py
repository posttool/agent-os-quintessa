"""Applies the memory capability's structured operations to the store.
The LLM decides what changes; this module only carries the changes out."""

from __future__ import annotations

from typing import Any

from quintessa.models import (
    Document,
    DocumentSection,
    DocumentStatus,
    EdgeType,
    KeyDate,
    MemoryEdge,
    MemoryNode,
    NodeType,
    Topic,
    TriggerSpec,
    TriggerType,
)
from quintessa.memory.store import MemoryStore
from quintessa.clock import now


def apply_operations(store: MemoryStore, operations: list[dict[str, Any]], event_id: str | None) -> list[str]:
    """Apply operations in order; returns one line per applied change.
    An operation missing the object it needs is skipped, not fatal, and its
    line starts with "skipped" so the step can report it."""
    applied: list[str] = []
    for op in operations:
        needs = _PAYLOAD.get(op["op"])
        if needs and not op.get(needs):
            applied.append(f"skipped {op['op']} {op.get('id', '')}: no {needs} given")
            continue
        try:
            line = _HANDLERS[op["op"]](store, op, event_id)
        except (KeyError, ValueError, TypeError) as e:
            applied.append(f"skipped {op['op']} {op.get('id', '')}: {type(e).__name__} {e}")
            continue
        if line:
            applied.append(line)
    return applied


def _upsert_node(store: MemoryStore, op: dict[str, Any], event_id: str | None) -> str:
    spec = op["node"]
    store.upsert_node(
        MemoryNode(
            id=op["id"],
            type=NodeType(spec["type"]),
            title=spec["title"],
            body=spec.get("body", ""),
            topic_id=spec.get("topic_id"),
            source_event_ids=[event_id] if event_id else [],
        )
    )
    return f"node {op['id']} saved"


def _delete_node(store: MemoryStore, op: dict[str, Any], _: str | None) -> str:
    return f"node {op['id']} deleted ({op.get('reason', '')})" if store.delete_node(op["id"]) else ""


def _upsert_edge(store: MemoryStore, op: dict[str, Any], _: str | None) -> str:
    spec = op["edge"]
    store.upsert_edge(MemoryEdge(spec["source_id"], spec["target_id"], EdgeType(spec["type"]), spec.get("note", "")))
    return f"edge {spec['source_id']} -{spec['type']}-> {spec['target_id']}"


def _delete_edge(store: MemoryStore, op: dict[str, Any], _: str | None) -> str:
    spec = op["edge"]
    if store.delete_edge(spec["source_id"], spec["target_id"], spec["type"]):
        return f"edge {spec['source_id']} -{spec['type']}-> {spec['target_id']} deleted"
    return ""


def _upsert_topic(store: MemoryStore, op: dict[str, Any], _: str | None) -> str:
    spec = op["topic"]
    existing = store.topics.get(op["id"])
    # Rules the user set win over the agent's defaults, so they are kept.
    user_rules = [t for t in existing.triggers if t.user_override] if existing else []
    agent_rules = [
        TriggerSpec(TriggerType(t["type"]), t["condition"], t.get("reasoning", "")) for t in spec.get("triggers", [])
    ]
    store.upsert_topic(
        Topic(
            id=op["id"],
            title=spec["title"],
            category=spec.get("category", ""),
            parent_id=spec.get("parent_id"),
            summary=spec.get("summary", ""),
            new_info=spec.get("new_info", ""),
            importance=spec.get("importance", ""),
            progress=float(spec.get("progress", 0.0)),
            progress_note=spec.get("progress_note", ""),
            due=spec.get("due", ""),
            triggers=user_rules + agent_rules,
            document_id=spec.get("document_id") or (existing.document_id if existing else None),
            archived=False,
            last_seen_at=existing.last_seen_at if existing else None,
        )
    )
    return f"topic {op['id']} saved"


def _archive_topic(store: MemoryStore, op: dict[str, Any], _: str | None) -> str:
    topic = store.topics.get(op["id"])
    if not topic:
        return ""
    topic.archived = True
    store.upsert_topic(topic)
    return f"topic {op['id']} archived ({op.get('reason', '')})"


def _upsert_document(store: MemoryStore, op: dict[str, Any], _: str | None) -> str:
    spec = op["document"]
    existing = store.documents.get(op["id"])
    doc = existing or Document(id=op["id"], title=spec["title"])
    doc.title = spec["title"]
    doc.topic_id = spec.get("topic_id") or doc.topic_id
    doc.description = spec.get("description", doc.description)
    doc.status = DocumentStatus(spec.get("status", doc.status.value))
    doc.progress_overview = spec.get("progress_overview", doc.progress_overview)
    doc.links = _merge(doc.links, spec.get("links", []))
    doc.observations = _merge(doc.observations, spec.get("observations", []))
    new_dates = [KeyDate(d["when"], d["label"], d.get("tentative", False)) for d in spec.get("key_dates", [])]
    doc.key_dates = [d for d in doc.key_dates if (d.when, d.label) not in {(n.when, n.label) for n in new_dates}] + new_dates
    store.upsert_document(doc)
    if doc.topic_id and doc.topic_id in store.topics and not store.topics[doc.topic_id].document_id:
        store.topics[doc.topic_id].document_id = doc.id
    return f"document {op['id']} saved"


def _upsert_section(store: MemoryStore, op: dict[str, Any], _: str | None) -> str:
    spec = op["section"]
    doc = store.documents.get(spec["document_id"])
    if not doc:
        return ""
    section = doc.section(op["id"])
    if section is None:
        section = DocumentSection(id=op["id"], title=spec["title"])
        doc.sections.append(section)
    section.title = spec["title"]
    section.overview = spec.get("overview", section.overview)
    section.status = spec.get("status", section.status)
    section.details = spec.get("details", section.details)
    section.actions_taken = _merge(section.actions_taken, spec.get("actions_taken", []))
    section.suggested_actions = spec.get("suggested_actions", section.suggested_actions)
    store.upsert_document(doc)
    return f"section {doc.id}/{op['id']} saved"


def _archive_document(store: MemoryStore, op: dict[str, Any], _: str | None) -> str:
    doc = store.documents.get(op["id"])
    if not doc:
        return ""
    doc.status = DocumentStatus.ARCHIVED
    store.upsert_document(doc)
    return f"document {op['id']} archived ({op.get('reason', '')})"


def _mark_topic_seen(store: MemoryStore, op: dict[str, Any], _: str | None) -> str:
    topic = store.topics.get(op["id"])
    if not topic:
        return ""
    topic.last_seen_at = now()
    topic.new_info = ""
    store.upsert_topic(topic)
    return f"topic {op['id']} marked seen"


def _merge(existing: list[str], new: list[str]) -> list[str]:
    return existing + [item for item in new if item not in existing]


_HANDLERS = {
    "upsert_node": _upsert_node,
    "delete_node": _delete_node,
    "upsert_edge": _upsert_edge,
    "delete_edge": _delete_edge,
    "upsert_topic": _upsert_topic,
    "archive_topic": _archive_topic,
    "upsert_document": _upsert_document,
    "upsert_section": _upsert_section,
    "archive_document": _archive_document,
    "mark_topic_seen": _mark_topic_seen,
}

# The object each operation reads; the rest only need `id`.
_PAYLOAD = {
    "upsert_node": "node",
    "upsert_edge": "edge",
    "delete_edge": "edge",
    "upsert_topic": "topic",
    "upsert_document": "document",
    "upsert_section": "section",
}

OPERATIONS = list(_HANDLERS)
