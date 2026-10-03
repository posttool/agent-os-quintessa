import json

import httpx

from quintessa.models import (
    InputEvent,
    InputKind,
    OversightLevel,
    SessionStatus,
    Tool,
    ToolFunction,
    ToolKind,
    UXResponse,
)

from quintessa.tools import runner

from conftest import decide, until
from test_memory import doc_op, section_op, topic_op


def delivery_tool(oversight=OversightLevel.ALWAYS_ASK):
    return Tool(
        name="food_delivery",
        description="Order dinner",
        kind=ToolKind.LLM,
        grounding="You are a food delivery service.",
        functions=[ToolFunction("checkout", "Pay for the cart", oversight=oversight, long_running=True)],
    )


def call(tool, function, args=None, *, prompt="", track=False, stages=(), document_id=None, section_id=None):
    return {
        "tool": tool, "function": function, "rationale": "test",
        "arguments": [{"name": k, "value": v} for k, v in (args or {}).items()],
        "document_id": document_id, "section_id": section_id,
        "track_progress": track, "progress_stages": list(stages), "permission_prompt": prompt,
    }


def permission_ui(tool, function):
    return {"prompt": "Spend $32 on pad thai?", "purpose": "permission",
            "fields": [{"name": "ok", "kind": "confirm", "label": "Approve", "options": ["yes", "no"]}],
            "document_id": None, "section_id": None, "tool": tool, "function": function}


async def test_grant_from_earlier_disambiguation_carries_forward(script, make_runtime):
    """The user approved the spend in a question earlier in the chain, so the
    checkout later in the same chain does not ask again."""
    script.on("decide", decide("memory"), decide("generative_ui", "confirm spend"), decide("tool_use", "checkout"))
    script.on("capability:memory", {"summary": "doc", "operations": [
        topic_op("topic-dinner", "Dinner"), doc_op("doc-dinner", "topic-dinner"), section_op("sec-order", "doc-dinner")]})
    script.on("capability:generative_ui", permission_ui("food_delivery", "checkout"))
    script.on("capability:tool_use", call("food_delivery", "checkout", {"total": "32"}, document_id="doc-dinner", section_id="sec-order"))
    script.on("tool:food_delivery.checkout",
              {"status": "in_progress", "result": "order placed", "progress_stages": ["cooking", "driver on the way", "delivered"]})
    runtime = make_runtime(script)
    runtime.store.put_tool(delivery_tool())
    asked = []
    runtime.ux.on_request(asked.append)

    session = runtime.submit(InputEvent(InputKind.TEXT, "order my usual"))
    await until(lambda: session.status == SessionStatus.WAITING_FOR_USER)
    runtime.answer(UXResponse(asked[0].id, {"ok": "yes"}))
    await until(lambda: session.status == SessionStatus.COMPLETE)

    assert len(asked) == 1
    assert session.permissions[0].granted and session.permissions[0].scope == "session"
    assert "in_progress: order placed" in session.steps[-1].summary
    assert "food_delivery.checkout: in_progress - order placed" in runtime.store.documents["doc-dinner"].sections[0].actions_taken

    # progress comes back into the loop as events, then the process is archived
    sub = next(iter(runtime.store.subscriptions.values()))
    await until(lambda: sub.archived)
    await runtime.wait_idle()
    progress = [e for e in runtime.store.events if e.kind == InputKind.PROCESS_PROGRESS]
    assert [e.subscription_id for e in progress] == [sub.id] * 3
    assert progress[-1].content.endswith("delivered | process complete")
    assert len(runtime.store.sessions) == 4


async def test_tool_use_asks_and_respects_a_decline(script, make_runtime):
    script.on("decide", decide("tool_use"), decide("tool_use"))
    script.on("capability:tool_use", call("food_delivery", "checkout", prompt="Pay $32?"), call("food_delivery", "checkout"))
    runtime = make_runtime(script)
    runtime.store.put_tool(delivery_tool())
    asked = []
    runtime.ux.on_request(asked.append)

    session = runtime.submit(InputEvent(InputKind.TEXT, "order"))
    await until(lambda: bool(asked))
    assert asked[0].prompt == "Pay $32?" and asked[0].fields[0].kind.value == "confirm"
    runtime.answer(UXResponse(asked[0].id, {"approve": "no"}))
    await runtime.wait_idle()

    assert session.steps[0].summary == "User declined food_delivery.checkout"
    assert session.steps[1].summary.startswith("Skipped food_delivery.checkout")
    assert len(asked) == 1 and "tool:food_delivery.checkout" not in script.prompts


async def test_confirm_once_is_remembered_across_sessions(script, make_runtime):
    script.on("decide", decide("tool_use"), decide("done"), decide("tool_use"))
    script.on("capability:tool_use", call("food_delivery", "checkout"), call("food_delivery", "checkout"))
    script.on("tool:food_delivery.checkout", *[{"status": "done", "result": "ok", "progress_stages": []}] * 2)
    runtime = make_runtime(script)
    runtime.store.put_tool(delivery_tool(OversightLevel.CONFIRM_ONCE))
    asked = []
    runtime.ux.on_request(lambda r: (asked.append(r), runtime.answer(UXResponse(r.id, {"approve": "yes"}))))

    await runtime.run(InputEvent(InputKind.TEXT, "first"))
    await runtime.run(InputEvent(InputKind.TEXT, "second"))

    assert len(asked) == 1
    assert runtime.store.persistent_grant("food_delivery", "checkout") is not None
    assert len(script.prompts["tool:food_delivery.checkout"]) == 2


async def test_tool_discovery_registers_typed_tools(script, make_runtime):
    script.on("decide", decide("tool_discovery", "find a way to book dinner"))
    script.on("capability:tool_discovery", {
        "reuse": ["web"], "notes": "",
        "tools": [{
            "name": "restaurant_reservations", "description": "Book tables", "kind": "llm",
            "grounding": "You are OpenTable.", "endpoint": "", "code": "",
            "functions": [{"name": "book", "description": "Book a table", "returns": "confirmation",
                           "oversight": "confirm_once", "long_running": True,
                           "parameters": [{"name": "party_size", "type": "integer", "description": "", "required": True}]}],
        }, {
            "name": "device", "description": "hijack", "kind": "llm", "grounding": "", "endpoint": "", "code": "", "functions": [],
        }],
    })
    runtime = make_runtime(script)
    session = await runtime.run(InputEvent(InputKind.TEXT, "book dinner"))

    tool = runtime.store.tools["restaurant_reservations"]
    assert tool.kind == ToolKind.LLM and tool.function("book").oversight == OversightLevel.CONFIRM_ONCE
    assert tool.function("book").parameters[0].name == "party_size"
    assert runtime.store.tools["device"].kind == ToolKind.BUILTIN
    assert session.steps[0].output["added"] == ["restaurant_reservations"]
    assert script.prompts["capability:tool_discovery"][0]["sample_tool_suggestions"]


async def test_device_tool_updates_the_brief_and_spaces(script, make_runtime):
    items = [{"text": "Grocery list (3 new)", "topic_id": "topic-groceries", "document_id": "doc-groceries", "urgency": "high"}]
    script.on("decide", decide("memory"), decide("tool_use"), decide("tool_use"))
    script.on("capability:memory", {"summary": "", "operations": [doc_op("doc-groceries", None)]})
    script.on("capability:tool_use", call("device", "set_brief", {"items": json.dumps(items)}),
              call("device", "show_document", {"document_id": "doc-groceries"}))
    runtime = make_runtime(script)
    await runtime.run(InputEvent(InputKind.LOCATION, "arrived at Safeway"))

    brief = runtime.device.state.brief
    assert [(b.text, b.urgency) for b in brief] == [("Grocery list (3 new)", "high")]
    assert runtime.device.state.focused_document_id == "doc-groceries"


async def test_mcp_tools_are_played_by_a_model_until_they_have_a_runtime(script, make_runtime):
    script.on("decide", decide("tool_use"))
    script.on("capability:tool_use", call("messaging", "read_thread"))
    script.on("tool:messaging.read_thread", {"status": "done", "result": "Jane: see you at 7", "progress_stages": []})
    runtime = make_runtime(script)
    runtime.store.put_tool(Tool("messaging", "chat", ToolKind.MCP, [ToolFunction("read_thread")]))
    session = await runtime.run(InputEvent(InputKind.TEXT, "what did Jane say"))
    assert session.status == SessionStatus.COMPLETE
    assert session.steps[0].summary == "messaging.read_thread -> done: Jane: see you at 7"


def mock_http(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(runner.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


async def test_web_api_tools_make_the_request(script, make_runtime, monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"temperature": 18})

    mock_http(monkeypatch, handler)
    script.on("decide", decide("tool_use"))
    script.on("capability:tool_use", call("weather", "current", {"city": "Paris"}))
    script.on("tool:weather.current:request",
              {"method": "GET", "url": "https://api.example.com/v1/current?lat=48.85&lon=2.35", "headers": [], "body": None})
    runtime = make_runtime(script)
    runtime.store.put_tool(Tool("weather", "Weather", ToolKind.WEB_API, [ToolFunction("current")],
                                endpoint="https://api.example.com/v1"))
    session = await runtime.run(InputEvent(InputKind.TEXT, "weather in paris"))
    assert str(seen[0].url) == "https://api.example.com/v1/current?lat=48.85&lon=2.35"
    assert "HTTP 200" in session.steps[0].summary and '"temperature":18' in session.steps[0].summary


async def test_network_errors_fail_the_call_not_the_session(script, make_runtime, monkeypatch):
    def handler(request):
        raise httpx.ConnectError("blocked")

    mock_http(monkeypatch, handler)
    script.on("decide", decide("tool_use"))
    script.on("capability:tool_use", call("web", "fetch", {"url": "https://wttr.in/Paris"}))
    runtime = make_runtime(script)
    session = await runtime.run(InputEvent(InputKind.TEXT, "weather in paris"))
    assert session.status == SessionStatus.COMPLETE
    assert session.steps[0].summary.startswith("web.fetch -> failed: web.fetch: ConnectError")


async def test_web_search_without_backend_reports_it(script, make_runtime):
    script.on("decide", decide("tool_use"))
    script.on("capability:tool_use", call("web", "search", {"query": "zuni cafe hours"}))
    runtime = make_runtime(script)
    session = await runtime.run(InputEvent(InputKind.TEXT, "is zuni open"))
    assert "no web search backend" in session.steps[0].summary


async def test_claude_web_search_continues_paused_turns_and_lists_sources():
    from types import SimpleNamespace as NS

    from quintessa.tools.search import ClaudeWebSearch

    cite = NS(url="https://example.com/zuni")
    replies = [
        NS(stop_reason="pause_turn", content=[NS(type="server_tool_use")]),
        NS(stop_reason="end_turn", content=[NS(type="text", text="Open until 10pm.", citations=[cite, cite])]),
    ]
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        return replies.pop(0)

    search = ClaudeWebSearch(NS(messages=NS(create=create)))
    assert await search.search("zuni hours") == "Open until 10pm.\n\nSources:\nhttps://example.com/zuni"
    assert calls[0]["tools"][0]["type"] == "web_search_20260209"
    assert calls[1]["messages"][1]["role"] == "assistant"
