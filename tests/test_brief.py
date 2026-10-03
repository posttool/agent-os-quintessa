import json

from quintessa.device import BriefAction, BriefItem
from quintessa.models import (
    Document,
    DocumentSection,
    DocumentStatus,
    InputEvent,
    InputKind,
    OversightLevel,
    SessionStatus,
    Topic,
)
from quintessa.tools.builtin import _set_brief

from conftest import decide, until
from test_tools import call, delivery_tool, permission_ui


def seed(runtime):
    store = runtime.store
    store.upsert_topic(Topic("topic-dentist", "Dentist", document_id="doc-dentist"))
    store.upsert_topic(Topic("topic-mom", "Call Mom tonight", summary="She asked you to call"))
    store.upsert_document(Document("doc-dentist", "Dentist", "topic-dentist", sections=[DocumentSection("sec-confirm", "Confirm")]))
    store.upsert_document(Document("doc-old", "Old trip", status=DocumentStatus.ARCHIVED))
    store.put_tool(delivery_tool())


async def test_brief_cards_keep_only_links_that_lead_somewhere(script, make_runtime):
    runtime = make_runtime(script)
    seed(runtime)
    items = [
        {"text": "Confirm the dentist", "topic_id": "topic-dentist", "section_id": "sec-confirm"},
        {"text": "Call Mom", "topic_id": "topic-mom", "detail": "Tonight after dinner"},
        {"text": "Old trip", "document_id": "doc-old", "section_id": "sec-x"},
        {"text": "Made up", "topic_id": "topic-nope", "document_id": "doc-nope"},
        {"urgency": "high"},
    ]
    result = await _set_brief({"items": json.dumps(items)}, runtime)

    brief = runtime.device.state.brief
    assert [(b.topic_id, b.document_id, b.section_id) for b in brief] == [
        ("topic-dentist", "doc-dentist", "sec-confirm"),  # document filled in from the topic
        ("topic-mom", None, None),
        (None, None, None),  # archived document dropped, and its section with it
        (None, None, None),
    ]
    assert brief[1].detail == "Tonight after dinner"
    assert len({b.id for b in brief}) == 4
    assert result.status == "done"
    assert "item 3: no open document doc-old, kept as a card" in result.result
    assert "item 3: no section sec-x" in result.result
    assert "item 4: no topic topic-nope" in result.result
    assert "item 5: skipped, it has no text" in result.result


async def test_brief_actions_must_name_an_installed_function(script, make_runtime):
    runtime = make_runtime(script)
    seed(runtime)
    items = [
        {"text": "Order dinner", "action": {"tool": "food_delivery", "function": "checkout",
                                            "arguments": {"total": 32, "dish": "pad thai"}, "label": "Order"}},
        {"text": "Call Mom", "action": {"tool": "phone", "function": "call", "label": "Call"}},
        {"text": "Pay", "action": {"tool": "food_delivery", "function": "refund"}},
    ]
    result = await _set_brief({"items": json.dumps(items)}, runtime)

    brief = runtime.device.state.brief
    assert brief[0].action == BriefAction("food_delivery", "checkout", "Order", {"total": "32", "dish": "pad thai"})
    assert brief[1].action is None and brief[2].action is None
    assert "item 2: action dropped: 'phone' is not installed" in result.result
    assert "item 3: action dropped: food_delivery has no function 'refund'" in result.result


async def test_a_tapped_action_carries_its_approval(script, make_runtime):
    """The tap approves the card's tool function, so the reasoning step runs it
    without asking, even for an always-ask function. Another tool still asks."""
    script.on("decide", decide("tool_use"), decide("generative_ui"), decide("tool_use"))
    script.on("capability:tool_use", call("food_delivery", "checkout", {"total": "32"}),
              call("groceries", "checkout"))
    script.on("capability:generative_ui", permission_ui("groceries", "checkout"))
    script.on("tool:food_delivery.checkout", {"status": "done", "result": "order placed", "progress_stages": []})
    runtime = make_runtime(script)
    runtime.store.put_tool(delivery_tool(OversightLevel.ALWAYS_ASK))
    groceries = delivery_tool()
    groceries.name = "groceries"
    runtime.store.put_tool(groceries)
    action = BriefAction("food_delivery", "checkout", "Order pad thai", {"total": "32"})
    runtime.device.set_brief([BriefItem("Dinner?", action=action)])
    asked = []
    runtime.ux.on_request(asked.append)

    session = runtime.start_brief_action(runtime.device.state.brief[0].id)
    await until(lambda: session.status == SessionStatus.WAITING_FOR_USER)

    assert session.steps[0].summary == "food_delivery.checkout -> done: order placed"
    assert 'tapped "Order pad thai"' in session.trigger.content and '{"total": "32"}' in session.trigger.content
    assert [r.tool for r in asked] == ["groceries"]  # only the tool the tap did not approve asks
    assert session.permissions[0].session_id == session.id and session.permissions[0].granted
    await runtime.cancel_tasks()


async def test_tapping_a_card_without_an_action_starts_nothing(script, make_runtime):
    runtime = make_runtime(script)
    runtime.device.set_brief([BriefItem("Bring an umbrella")])
    assert runtime.start_brief_action(runtime.device.state.brief[0].id) is None
    assert runtime.start_brief_action("brf-gone") is None


async def test_questions_know_their_topic(script, make_runtime):
    script.on("decide", decide("generative_ui"))
    script.on("capability:generative_ui", {**permission_ui(None, None), "purpose": "disambiguation",
                                           "document_id": "doc-dentist", "topic_id": None})
    runtime = make_runtime(script)
    seed(runtime)
    asked = []
    runtime.ux.on_request(asked.append)
    session = runtime.submit(InputEvent(InputKind.TEXT, "the dentist called"))
    await until(lambda: session.status == SessionStatus.WAITING_FOR_USER)
    assert asked[0].topic_id == "topic-dentist"  # taken from its document
    await runtime.cancel_tasks()
