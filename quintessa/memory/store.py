from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable

from quintessa.clock import now
from quintessa.models import (
    Document,
    InputEvent,
    MemoryEdge,
    MemoryNode,
    Permission,
    ReasoningSession,
    Subscription,
    Tool,
    Topic,
)
from quintessa.serde import from_dict, to_dict

Listener = Callable[[str, dict[str, Any]], None]


class MemoryStore:
    """The shared memory space every reasoning loop reads and writes: the
    knowledge graph, the topic index, documents, tools, permissions, process
    subscriptions, raw events (for audit) and session traces.

    It knows nothing about any design system or device; surfaces subscribe
    through `listen`."""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self._listeners: list[Listener] = []
        self.clear()

    def clear(self) -> None:
        self.nodes: dict[str, MemoryNode] = {}
        self.edges: dict[tuple[str, str, str], MemoryEdge] = {}
        self.topics: dict[str, Topic] = {}
        self.documents: dict[str, Document] = {}
        self.tools: dict[str, Tool] = {}
        self.permissions: list[Permission] = []
        self.subscriptions: dict[str, Subscription] = {}
        self.events: list[InputEvent] = []
        self.sessions: dict[str, ReasoningSession] = {}
        self._emit("cleared", {})

    # --- change notifications -------------------------------------------

    def listen(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def _emit(self, kind: str, payload: dict[str, Any]) -> None:
        for listener in getattr(self, "_listeners", []):
            listener(kind, payload)

    # --- writes (callers hold `lock` when they batch several) -------------

    def record_event(self, event: InputEvent) -> None:
        self.events.append(event)
        self._emit("event", to_dict(event))

    def put_session(self, session: ReasoningSession) -> None:
        self.sessions[session.id] = session
        self._emit("session", {"id": session.id, "status": session.status.value})

    def upsert_node(self, node: MemoryNode) -> MemoryNode:
        existing = self.nodes.get(node.id)
        if existing:
            node.created_at = existing.created_at
            node.source_event_ids = sorted(set(existing.source_event_ids) | set(node.source_event_ids))
        node.updated_at = now()
        self.nodes[node.id] = node
        self._emit("node", to_dict(node))
        return node

    def delete_node(self, node_id: str) -> bool:
        removed = self.nodes.pop(node_id, None)
        for key in [k for k in self.edges if node_id in (k[0], k[1])]:
            del self.edges[key]
        if removed:
            self._emit("node_deleted", {"id": node_id})
        return removed is not None

    def upsert_edge(self, edge: MemoryEdge) -> None:
        self.edges[edge.key] = edge
        self._emit("edge", to_dict(edge))

    def delete_edge(self, source_id: str, target_id: str, edge_type: str) -> bool:
        removed = self.edges.pop((source_id, target_id, edge_type), None)
        if removed:
            self._emit("edge_deleted", to_dict(removed))
        return removed is not None

    def upsert_topic(self, topic: Topic) -> Topic:
        topic.updated_at = now()
        self.topics[topic.id] = topic
        self._emit("topic", to_dict(topic))
        return topic

    def upsert_document(self, document: Document) -> Document:
        document.updated_at = now()
        self.documents[document.id] = document
        self._emit("document", to_dict(document))
        return document

    def put_tool(self, tool: Tool) -> None:
        self.tools[tool.name] = tool
        self._emit("tool", to_dict(tool))

    def delete_tool(self, name: str) -> bool:
        removed = self.tools.pop(name, None)
        if removed:
            self._emit("tool_deleted", {"name": name})
        return removed is not None

    def add_permission(self, permission: Permission) -> None:
        self.permissions.append(permission)
        self._emit("permission", to_dict(permission))

    def put_subscription(self, subscription: Subscription) -> None:
        self.subscriptions[subscription.id] = subscription
        self._emit("subscription", to_dict(subscription))

    # --- reads --------------------------------------------------------------

    def persistent_grant(self, tool: str, function: str) -> Permission | None:
        matches = [p for p in self.permissions if p.tool == tool and p.function == function and p.scope == "persistent"]
        return matches[-1] if matches else None

    def snapshot(self) -> dict[str, Any]:
        """The state handed to the LLM. Archived topics and documents are left out."""
        return {
            "nodes": [to_dict(n) for n in self.nodes.values()],
            "edges": [to_dict(e) for e in self.edges.values()],
            "topics": [to_dict(t) for t in self.topics.values() if not t.archived],
            "documents": [to_dict(d) for d in self.documents.values() if d.status.value != "archived"],
            "tools": [to_dict(t) for t in self.tools.values()],
            "permissions": [to_dict(p) for p in self.permissions],
            "active_processes": [to_dict(s) for s in self.subscriptions.values() if not s.archived],
        }

    # --- persistence ----------------------------------------------------------

    def save(self, path: str | Path) -> None:
        data = {
            "nodes": [to_dict(n) for n in self.nodes.values()],
            "edges": [to_dict(e) for e in self.edges.values()],
            "topics": [to_dict(t) for t in self.topics.values()],
            "documents": [to_dict(d) for d in self.documents.values()],
            "tools": [to_dict(t) for t in self.tools.values()],
            "permissions": [to_dict(p) for p in self.permissions],
            "subscriptions": [to_dict(s) for s in self.subscriptions.values()],
            "events": [to_dict(e) for e in self.events],
            "sessions": [to_dict(s) for s in self.sessions.values()],
        }
        Path(path).write_text(json.dumps(data, indent=2))

    def load(self, path: str | Path) -> None:
        data = json.loads(Path(path).read_text())
        self.clear()
        for n in data["nodes"]:
            node = from_dict(MemoryNode, n)
            self.nodes[node.id] = node
        for e in data["edges"]:
            edge = from_dict(MemoryEdge, e)
            self.edges[edge.key] = edge
        for t in data["topics"]:
            topic = from_dict(Topic, t)
            self.topics[topic.id] = topic
        for d in data["documents"]:
            doc = from_dict(Document, d)
            self.documents[doc.id] = doc
        for t in data["tools"]:
            tool = from_dict(Tool, t)
            self.tools[tool.name] = tool
        self.permissions = [from_dict(Permission, p) for p in data["permissions"]]
        for s in data["subscriptions"]:
            sub = from_dict(Subscription, s)
            self.subscriptions[sub.id] = sub
        self.events = [from_dict(InputEvent, e) for e in data["events"]]
        for s in data["sessions"]:
            session = from_dict(ReasoningSession, s)
            self.sessions[session.id] = session
        self._emit("loaded", {})
