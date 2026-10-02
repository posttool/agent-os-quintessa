import json
from datetime import datetime, timedelta, timezone

from quintessa.device import FULL, DocumentFocus
from quintessa.device.focus import resolve_view
from quintessa.memory import MemoryStore
from quintessa.memory.apply import apply_operations
from quintessa.models import Document, DocumentSection, InputEvent, InputKind, Topic, UXPurpose, UXRequest

from conftest import decide
from test_api import api  # noqa: F401  (fixture)
from test_memory import doc_op, section_op, topic_op
from test_tools import call

T0 = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def section(id, status="in progress", next_steps=("book",), updated=0):
    return DocumentSection(id, id.title(), status=status, suggested_actions=list(next_steps), updated_at=at(updated))


def trip(*sections):
    return Document("doc-trip", "Trip", topic_id="topic-trip", sections=list(sections))


def question(section_id):
    return UXRequest("s1", UXPurpose.DISAMBIGUATION, "?", document_id="doc-trip", section_id=section_id)


def test_rule_shows_the_first_open_section_with_a_next_step():
    doc = trip(section("flights", status="complete"), section("hotel", next_steps=()), section("car"), section("dinner"))
    view = resolve_view(doc, None, [], None)
    assert view["section_ids"] == ["car"] and view["set_by"] == "rule" and view["mode"] == "focused"


def test_rule_puts_questions_before_changes_and_caps_at_two():
    doc = trip(section("flights", updated=10), section("hotel", updated=10), section("car"), section("dinner"))
    topic = Topic("topic-trip", "Trip", last_seen_at=at(5))
    view = resolve_view(doc, None, [question("dinner")], topic)
    assert view["section_ids"] == ["dinner", "flights"]
    assert view["changed_section_ids"] == ["flights", "hotel"]


def test_chosen_focus_holds_until_another_section_changes():
    focus = DocumentFocus("doc-trip", ["hotel"], set_by="user", updated_at=at(5))
    doc = trip(section("flights"), section("hotel", updated=8))
    # the focused section itself changing keeps the focus
    assert resolve_view(doc, focus, [], None)["section_ids"] == ["hotel"]
    assert resolve_view(doc, focus, [], None)["set_by"] == "user"

    doc.sections[0].updated_at = at(9)
    view = resolve_view(doc, focus, [], None)
    assert view["set_by"] == "rule" and view["section_ids"] == ["flights"]


def test_full_mode_holds_and_ignores_missing_sections():
    doc = trip(section("flights", updated=20), section("hotel"))
    assert resolve_view(doc, DocumentFocus("doc-trip", [], FULL, updated_at=at(5)), [], None)["mode"] == FULL
    gone = DocumentFocus("doc-trip", ["deleted"], reason="why", updated_at=at(30))
    view = resolve_view(doc, gone, [], None)
    assert view["section_ids"] == ["flights"] and view["set_by"] == "rule"


def test_section_timestamp_moves_only_when_content_changes():
    store = MemoryStore()
    apply_operations(store, [doc_op("doc-dinner", None), section_op("sec-place", "doc-dinner")], None)
    first = store.documents["doc-dinner"].section("sec-place").updated_at
    apply_operations(store, [section_op("sec-place", "doc-dinner")], None)
    assert store.documents["doc-dinner"].section("sec-place").updated_at == first
    apply_operations(store, [section_op("sec-place", "doc-dinner", actions=["called"])], None)
    assert store.documents["doc-dinner"].section("sec-place").updated_at > first


async def test_device_tool_focuses_sections_and_rejects_unknown_ones(script, make_runtime):
    script.on("decide", decide("memory"), decide("tool_use"), decide("tool_use"), decide("tool_use"))
    script.on("capability:memory", {"summary": "", "operations": [
        doc_op("doc-dinner", None), section_op("sec-place", "doc-dinner"), section_op("sec-time", "doc-dinner")]})
    script.on(
        "capability:tool_use",
        call("device", "show_document", {"document_id": "doc-dinner", "section_ids": json.dumps(["sec-nope"])}),
        call("device", "show_document", {"document_id": "doc-dinner", "section_ids": json.dumps(["sec-time"]),
                                          "reason": "Jane prefers Wednesday"}),
        call("device", "show_document", {"document_id": "doc-dinner", "mode": "sideways"}),
    )
    runtime = make_runtime(script)
    session = await runtime.run(InputEvent(InputKind.MESSAGE, "Jane: wednesday better", sender="Jane"))

    assert "has no sections ['sec-nope']" in session.steps[1].summary
    assert "mode must be" in session.steps[3].summary
    on_screen = runtime.on_screen()
    assert on_screen["section_ids"] == ["sec-time"] and on_screen["reason"] == "Jane prefers Wednesday"
    # the agent sees what is on screen
    assert script.prompts["decide"][-1]["on_screen"]["section_ids"] == ["sec-time"]


async def test_user_view_is_saved_and_survives_restore(api, script):  # noqa: F811
    agent = await api.host.agent("maya")
    apply_operations(agent.store, [doc_op("doc-dinner", None), section_op("sec-place", "doc-dinner"),
                                   section_op("sec-time", "doc-dinner")], None)

    r = await api.post("/api/view?user=maya", json={"document_id": "doc-dinner", "section_ids": ["sec-time"]})
    assert r.status_code == 200 and r.json()["set_by"] == "user"
    assert (await api.post("/api/view?user=maya", json={"document_id": "doc-dinner", "section_ids": ["x"]})).status_code == 422
    assert (await api.post("/api/view?user=maya", json={"document_id": "doc-none"})).status_code == 404

    await api.post("/api/view?user=maya", json={"document_id": "doc-dinner", "section_ids": [], "mode": "full"})
    saved = (await api.get("/api/export?user=maya")).text
    await api.post("/api/clear?user=maya")
    assert (await api.get("/api/state?user=maya")).json()["views"] == {}
    assert (await api.post("/api/restore?user=maya", content=saved)).status_code == 200
    state = (await api.get("/api/state?user=maya")).json()
    assert state["views"]["doc-dinner"]["mode"] == FULL
    assert state["device"]["focused_document_id"] == "doc-dinner"


def test_user_can_fold_everything_and_open_more_than_two():
    doc = trip(section("flights"), section("hotel"), section("car"))
    assert resolve_view(doc, DocumentFocus("doc-trip", [], set_by="user", updated_at=at(5)), [], None)["section_ids"] == []
    many = DocumentFocus("doc-trip", ["flights", "hotel", "car"], set_by="user", updated_at=at(5))
    assert len(resolve_view(doc, many, [], None)["section_ids"]) == 3
    agent = DocumentFocus("doc-trip", ["flights", "hotel", "car"], updated_at=at(5))
    assert len(resolve_view(doc, agent, [], None)["section_ids"]) == 2


async def test_back_to_focus_and_seen_pins_what_was_shown(api):  # noqa: F811
    agent = await api.host.agent("maya")
    apply_operations(agent.store, [topic_op("topic-dinner", "Dinner"), doc_op("doc-dinner", "topic-dinner"),
                                   section_op("sec-place", "doc-dinner"), section_op("sec-time", "doc-dinner")], None)
    await api.post("/api/view?user=maya", json={"document_id": "doc-dinner", "section_ids": []})
    r = await api.post("/api/view?user=maya", json={"document_id": "doc-dinner", "section_ids": None})
    assert r.json()["set_by"] == "rule" and r.json()["section_ids"] == ["sec-place"]

    assert (await api.post("/api/topics/topic-dinner/seen?user=maya")).status_code == 200
    assert agent.device.state.focus["doc-dinner"].section_ids == ["sec-place"]
