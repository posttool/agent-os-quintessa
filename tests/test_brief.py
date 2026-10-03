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


# --- keeping the brief true -------------------------------------------------

from datetime import timedelta  # noqa: E402

from quintessa.clock import now  # noqa: E402
from quintessa.device.freshness import brief_context  # noqa: E402
from quintessa.tools.builtin import _update_brief  # noqa: E402

from test_memory import topic_op  # noqa: E402


def refresh(*cards, questions=()):
    return {"cards": [{"id": i, "verdict": v, "text": text, "detail": "", "urgency": "", "expires_at": None,
                       "drop_action": False, "reason": "test"} for i, v, text in cards],
            "questions": [{"id": i, "withdraw": True, "reason": "Mom texted"} for i in questions]}


async def test_a_topic_has_one_card(script, make_runtime):
    runtime = make_runtime(script)
    seed(runtime)
    await _set_brief({"items": json.dumps([{"text": "Call Mom", "topic_id": "topic-mom"}])}, runtime)
    first = runtime.device.state.brief[0]

    result = await _update_brief({"put": json.dumps([{"text": "Call Mom after 8", "topic_id": "topic-mom"},
                                                     {"text": "Confirm the dentist", "topic_id": "topic-dentist"}])},
                                 runtime)
    brief = runtime.device.state.brief
    assert [b.text for b in brief] == ["Call Mom after 8", "Confirm the dentist"]
    assert brief[0].id == first.id and brief[0].created_at == first.created_at
    assert f"replaced {first.id} (Call Mom -> Call Mom after 8)" in result.result

    result = await _update_brief({"remove": json.dumps([first.id, "brf-gone"])}, runtime)
    assert [b.text for b in runtime.device.state.brief] == ["Confirm the dentist"]
    assert "no card brf-gone to remove" in result.result

    # a rebuilt brief keeps one card per topic, and the id of the card it replaces
    dentist = runtime.device.state.brief[0].id
    result = await _set_brief({"items": json.dumps([{"text": "Dentist at 3", "topic_id": "topic-dentist"},
                                                    {"text": "Dentist at 4", "topic_id": "topic-dentist"}])}, runtime)
    assert [(b.id, b.text) for b in runtime.device.state.brief] == [(dentist, "Dentist at 4")]
    assert "item 2: replaces item 1" in result.result


async def test_cards_expire(script, make_runtime):
    runtime = make_runtime(script)
    past, future = (now() - timedelta(minutes=5)).isoformat(), (now() + timedelta(hours=1)).isoformat()
    result = await _set_brief({"items": json.dumps([
        {"text": "Leave by 3pm", "expires_at": past},
        {"text": "Umbrella", "expires_at": future},
        {"text": "Soon", "expires_at": "after lunch"},
    ])}, runtime)
    assert "item 3: expires_at dropped: 'after lunch' is not an ISO time" in result.result
    assert [c["text"] for c in brief_context(runtime)["brief"]] == ["Umbrella", "Soon"]
    assert [b.text for b in runtime.device.state.brief] == ["Umbrella", "Soon"]


async def test_the_agent_sees_the_brief_and_what_went_stale(script, make_runtime):
    runtime = make_runtime(script)
    seed(runtime)
    runtime.device.set_brief([BriefItem("Call Mom", "topic-mom"), BriefItem("Confirm the dentist", "topic-dentist")])
    runtime.store.upsert_topic(Topic("topic-mom", "Call Mom tonight", summary="She called back"))
    script.on("brief_refresh", refresh())
    await runtime.run(InputEvent(InputKind.TEXT, "hi"))

    shown = script.prompts["decide"][0]["brief"]
    assert [(c["text"], c["stale"]) for c in shown] == [
        ("Call Mom", "its topic changed after the card was written"), ("Confirm the dentist", "")]
    assert script.prompts["decide"][0]["questions_waiting"] == []


async def test_a_location_change_rewrites_the_card_it_changes(script, make_runtime):
    """The user is farther away than the card assumed: the memory step changes
    the topic, and the end-of-session refresh rewrites only that topic's card."""
    runtime = make_runtime(script)
    seed(runtime)
    runtime.device.set_brief([BriefItem("Leave by 2:30 for the dentist", "topic-dentist"), BriefItem("Call Mom", "topic-mom")])
    card, other = runtime.device.state.brief
    script.on("decide", decide("memory"))
    script.on("capability:memory", {"summary": "moved", "operations": [topic_op("topic-dentist", "Dentist, 40 minutes away")]})
    script.on("brief_refresh", lambda p: refresh((p["cards"][0]["id"], "rewrite", "Leave now, the dentist is 40 minutes away")))

    session = await runtime.run(InputEvent(InputKind.LOCATION, "At the office, 40 minutes from the dentist", source="ambient"))

    assert [c["text"] for c in script.prompts["brief_refresh"][0]["cards"]] == ["Leave by 2:30 for the dentist"]
    assert [(b.id, b.text) for b in runtime.device.state.brief] == [
        (card.id, "Leave now, the dentist is 40 minutes away"), (other.id, "Call Mom")]
    assert session.steps[-1].capability == "brief_refresh"
    assert "rewrote" in session.steps[-1].summary
    assert brief_context(runtime)["brief"][0]["stale"] == ""  # fresh again; no refresh next time


async def test_news_that_settles_a_topic_clears_its_card_and_question(script, make_runtime):
    script.on("decide", decide("generative_ui"))
    script.on("capability:generative_ui", {**permission_ui(None, None), "purpose": "disambiguation",
                                           "prompt": "Call Mom at 7 or 8?", "topic_id": "topic-mom"})
    runtime = make_runtime(script)
    seed(runtime)
    runtime.device.set_brief([BriefItem("Call Mom", "topic-mom")])
    asking = runtime.submit(InputEvent(InputKind.TEXT, "remind me to call mom"))
    await until(lambda: asking.status == SessionStatus.WAITING_FOR_USER)
    question = next(iter(runtime.ux.pending))

    script.on("decide", decide("memory"))
    script.on("capability:memory", {"summary": "done", "operations": [topic_op("topic-mom", "Mom: talked already")]})
    script.on("brief_refresh", lambda p: refresh((p["cards"][0]["id"], "remove", ""), questions=[p["questions"][0]["id"]]))
    texted = runtime.submit(InputEvent(InputKind.MESSAGE, "Mom: no need to call, we talked at lunch", source="ambient"))
    await until(lambda: texted.status == SessionStatus.COMPLETE and asking.status == SessionStatus.COMPLETE)

    assert runtime.device.state.brief == []
    assert runtime.ux.pending == {}
    assert f"withdrew question {question}" in texted.steps[-1].summary
    assert "withdrew it before the user answered (Mom texted)" in asking.steps[0].summary


async def test_cards_the_session_wrote_are_not_refreshed(script, make_runtime):
    """A session that changes a topic and then writes its card leaves nothing
    stale, so no refresh call is made; the card remembers its cause."""
    runtime = make_runtime(script)
    seed(runtime)
    script.on("decide", decide("memory"), decide("tool_use"))
    script.on("capability:memory", {"summary": "s", "operations": [topic_op("topic-mom", "Call Mom at 8")]})
    script.on("capability:tool_use", call("device", "update_brief", {"put": json.dumps([{"text": "Call Mom at 8", "topic_id": "topic-mom"}])}))
    event = InputEvent(InputKind.TEXT, "mom says 8 is better")
    session = await runtime.run(event)

    assert [s.capability for s in session.steps] == ["memory", "tool_use"]
    assert runtime.device.state.brief[0].source_event_id == event.id


async def test_seeing_a_topic_does_not_make_its_card_stale(script, make_runtime):
    from quintessa.memory.apply import apply_operations

    runtime = make_runtime(script)
    seed(runtime)
    runtime.device.set_brief([BriefItem("Call Mom", "topic-mom")])
    apply_operations(runtime.store, [{"op": "mark_topic_seen", "id": "topic-mom"}], None)
    assert brief_context(runtime)["brief"][0]["stale"] == ""
