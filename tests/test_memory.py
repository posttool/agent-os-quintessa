from quintessa.memory import MemoryStore
from quintessa.memory.apply import apply_operations
from quintessa.models import DocumentStatus, TriggerSpec, TriggerType


def node_op(id, title, type="personal_preference", body=""):
    return {"op": "upsert_node", "id": id, "reason": "", "node": {"type": type, "title": title, "body": body, "topic_id": None},
            "edge": None, "topic": None, "document": None, "section": None}


def edge_op(op, source, target, type="relates_to"):
    return {"op": op, "id": "", "reason": "", "node": None, "topic": None, "document": None, "section": None,
            "edge": {"source_id": source, "target_id": target, "type": type, "note": ""}}


def topic_op(id, title, triggers=(), document_id=None):
    return {"op": "upsert_topic", "id": id, "reason": "", "node": None, "edge": None, "document": None, "section": None,
            "topic": {"title": title, "category": "", "parent_id": None, "summary": "s", "new_info": "Jane wants Zuni",
                      "importance": "", "progress": 0.2, "progress_note": "", "due": "next week",
                      "triggers": [{"type": t, "condition": c, "reasoning": ""} for t, c in triggers],
                      "document_id": document_id}}


def doc_op(id, topic_id, status="active", observations=()):
    return {"op": "upsert_document", "id": id, "reason": "", "node": None, "edge": None, "topic": None, "section": None,
            "document": {"title": "Dinner", "topic_id": topic_id, "description": "d", "status": status,
                         "progress_overview": "", "links": [], "observations": list(observations),
                         "key_dates": [{"when": "Tuesday 7pm", "label": "dinner", "tentative": True}]}}


def section_op(id, doc_id, actions=()):
    return {"op": "upsert_section", "id": id, "reason": "", "node": None, "edge": None, "topic": None, "document": None,
            "section": {"document_id": doc_id, "title": "Pick a place", "overview": "", "status": "in progress",
                        "details": "", "actions_taken": list(actions), "suggested_actions": ["book"]}}


def simple(op, id):
    return {"op": op, "id": id, "reason": "done", "node": None, "edge": None, "topic": None, "document": None, "section": None}


def test_graph_documents_and_topics():
    store = MemoryStore()
    applied = apply_operations(
        store,
        [
            node_op("pref-thai", "Likes Thai food"),
            node_op("person-jane", "Jane", type="person"),
            edge_op("upsert_edge", "person-jane", "pref-thai"),
            topic_op("topic-dinner", "Dinner Plans", [("time", "day before"), ("time", "day of")]),
            doc_op("doc-dinner", "topic-dinner", observations=["Jane: zuni?"]),
            section_op("sec-place", "doc-dinner", ["asked Jane"]),
            section_op("sec-place", "doc-dinner", ["asked Jane", "checked hours"]),
        ],
        event_id="evt_1",
    )
    assert len(applied) == 7
    assert store.nodes["pref-thai"].source_event_ids == ["evt_1"]
    assert store.topics["topic-dinner"].document_id == "doc-dinner"
    doc = store.documents["doc-dinner"]
    assert doc.status == DocumentStatus.ACTIVE and doc.key_dates[0].tentative
    assert len(doc.sections) == 1 and doc.sections[0].actions_taken == ["asked Jane", "checked hours"]

    apply_operations(store, [doc_op("doc-dinner", "topic-dinner", observations=["Jane: zuni?", "Jane: 7pm"])], None)
    assert store.documents["doc-dinner"].observations == ["Jane: zuni?", "Jane: 7pm"]
    assert len(store.documents["doc-dinner"].sections) == 1


def test_delete_node_removes_its_edges():
    store = MemoryStore()
    apply_operations(store, [node_op("a", "A"), node_op("b", "B"), edge_op("upsert_edge", "a", "b")], None)
    apply_operations(store, [simple("delete_node", "a")], None)
    assert "a" not in store.nodes and not store.edges


def test_user_trigger_overrides_survive_agent_updates():
    store = MemoryStore()
    apply_operations(store, [topic_op("topic-academics", "Academics", [("time", "mornings")])], None)
    store.topics["topic-academics"].triggers.append(TriggerSpec(TriggerType.TIME, "never on weekends", user_override=True))
    apply_operations(store, [topic_op("topic-academics", "Academics", [("location", "at school")])], None)
    conditions = [(t.condition, t.user_override) for t in store.topics["topic-academics"].triggers]
    assert conditions == [("never on weekends", True), ("at school", False)]


def test_archived_items_leave_the_snapshot_and_seen_clears_new_info():
    store = MemoryStore()
    apply_operations(store, [topic_op("t1", "Party"), doc_op("d1", "t1"), topic_op("t2", "Sofa")], None)
    apply_operations(store, [simple("archive_topic", "t1"), simple("archive_document", "d1"), simple("mark_topic_seen", "t2")], None)
    snap = store.snapshot()
    assert [t["id"] for t in snap["topics"]] == ["t2"] and snap["documents"] == []
    assert store.topics["t2"].new_info == "" and store.topics["t2"].last_seen_at is not None


def test_save_and_load(tmp_path):
    store = MemoryStore()
    apply_operations(store, [node_op("a", "A"), node_op("b", "B"), edge_op("upsert_edge", "a", "b"),
                             topic_op("t", "T"), doc_op("d", "t"), section_op("s", "d")], "evt")
    store.save(tmp_path / "m.json")
    loaded = MemoryStore()
    loaded.load(tmp_path / "m.json")
    assert loaded.snapshot() == store.snapshot()


def test_listeners_see_changes():
    store = MemoryStore()
    seen = []
    store.listen(lambda kind, payload: seen.append(kind))
    apply_operations(store, [node_op("a", "A")], None)
    store.clear()
    assert seen == ["node", "cleared"]


def test_operation_missing_its_object_is_skipped_not_fatal():
    store = MemoryStore()
    apply_operations(store, [node_op("a", "A"), node_op("b", "B"), edge_op("upsert_edge", "a", "b")], None)
    bad_delete = {**edge_op("delete_edge", "a", "b"), "id": "edge-a-b", "edge": None}
    bad_topic = {**topic_op("t1", "Party"), "topic": None}
    applied = apply_operations(store, [bad_delete, bad_topic, node_op("c", "C")], None)
    assert applied[0] == "skipped delete_edge edge-a-b: no edge given"
    assert applied[1] == "skipped upsert_topic t1: no topic given"
    assert applied[2] == "node c saved"
    assert "c" in store.nodes and "t1" not in store.topics
