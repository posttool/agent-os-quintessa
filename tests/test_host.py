import json

import pytest
from conftest import decide, until
from test_memory import doc_op, node_op, topic_op
from test_tools import call, delivery_tool

from quintessa.models import InputEvent, InputKind, OversightLevel, SessionStatus, UXResponse
from quintessa.state import FileStateBackend, InMemoryStateBackend, StateFormatError
from quintessa.state.snapshot import INTERRUPTED


def remember(*ops):
    return {"summary": "saved", "operations": list(ops)}


async def test_each_user_has_their_own_agent_state(script, make_host):
    script.on("decide", decide("memory"), decide("done"), decide("memory"))
    script.on(
        "capability:memory",
        remember(node_op("pref-thai", "Likes Thai")),
        remember(node_op("pref-sushi", "Likes sushi")),
    )
    host = make_host(script, InMemoryStateBackend())

    await host.run("maya", InputEvent(InputKind.TEXT, "I love Thai"))
    await host.run("tunde", InputEvent(InputKind.TEXT, "I love sushi"))

    maya, tunde = await host.agent("maya"), await host.agent("tunde")
    assert set(maya.store.nodes) == {"pref-thai"} and set(tunde.store.nodes) == {"pref-sushi"}
    assert maya is not tunde and maya.device is not tunde.device and maya.store.tools is not tunde.store.tools
    assert len(maya.store.events) == len(tunde.store.events) == 1
    assert host.loaded_users == ["maya", "tunde"]
    # the model only ever saw the requesting user's memory
    assert script.prompts["capability:memory"][1]["memory"]["nodes"] == []


async def test_state_survives_a_platform_restart(script, make_host, tmp_path):
    backend = FileStateBackend(tmp_path / "agents")
    script.on("decide", decide("memory"))
    script.on("capability:memory", remember(topic_op("topic-dinner", "Dinner"), doc_op("doc-dinner", "topic-dinner")))
    host = make_host(script, backend)
    session = await host.run("maya", InputEvent(InputKind.TEXT, "dinner with Jane"))
    await until(lambda: backend.path_for("maya").exists())
    await host.shutdown()

    restarted = make_host(script, FileStateBackend(tmp_path / "agents"))
    agent = await restarted.agent("maya")
    assert "doc-dinner" in agent.store.documents
    assert agent.store.sessions[session.id].steps[0].capability == "memory"
    assert agent.store.events[0].content == "dinner with Jane"
    assert set(agent.store.tools) == {"web", "device"}
    assert await restarted.backend.list_users() == ["maya"]


async def test_state_survives_a_restart_in_the_database(script, make_host, open_sql):
    script.on("decide", decide("memory"))
    script.on("capability:memory", remember(topic_op("topic-dinner", "Dinner"), doc_op("doc-dinner", "topic-dinner")))
    host = make_host(script, open_sql())
    session = await host.run("maya", InputEvent(InputKind.TEXT, "dinner with Jane"))
    agent = await host.agent("maya")
    agent.set_preferences(jev_drive=True)
    agent.persona = {"persona_id": "p_maya", "date": "2026-05-26", "profile": {"name": "Maya Okafor"}}
    before = await host.export_state("maya")
    await host.shutdown()

    restarted = make_host(script, open_sql())
    agent = await restarted.agent("maya")
    assert "doc-dinner" in agent.store.documents and agent.store.events[0].content == "dinner with Jane"
    assert agent.store.sessions[session.id].steps[0].capability == "memory"
    assert agent.preferences.jev_drive is True and agent.persona["profile"]["name"] == "Maya Okafor"
    after = await restarted.export_state("maya")
    assert {k: v for k, v in after.items() if k != "saved_at"} == {k: v for k, v in before.items() if k != "saved_at"}
    assert await restarted.backend.list_users() == ["maya"]


async def test_restart_stops_interrupted_sessions_and_resumes_processes(script, make_host, make_backend):
    backend = make_backend()
    script.on("decide", decide("tool_use"), decide("generative_ui"))
    script.on("capability:tool_use", call("food_delivery", "checkout"))
    script.on(
        "tool:food_delivery.checkout",
        {"status": "in_progress", "result": "placed", "progress_stages": ["cooking", "delivered"]},
    )
    script.on(
        "capability:generative_ui",
        {
            "prompt": "Tip?",
            "purpose": "information",
            "context": "",
            "fields": [],
            "document_id": None,
            "section_id": None,
            "topic_id": None,
            "tool": None,
            "function": None,
        },
    )
    host = make_host(script, backend)
    agent = await host.agent("maya")
    agent.store.put_tool(delivery_tool(OversightLevel.AUTO))
    agent.ambient.process_interval = 3600  # the process will not advance before the restart
    session = agent.submit(InputEvent(InputKind.TEXT, "order dinner"))
    await until(lambda: session.status == SessionStatus.WAITING_FOR_USER)
    await host.shutdown()

    restarted = make_host(script, make_backend())
    agent = await restarted.agent("maya")
    stopped = agent.store.sessions[session.id]
    assert stopped.status == SessionStatus.STOPPED and stopped.steps[-1].error == INTERRUPTED
    assert agent.device.state.open_ux_ids == [] and not agent.device.state.island.active
    subscription = next(iter(agent.store.subscriptions.values()))
    await until(lambda: subscription.archived)
    await agent.wait_idle()
    progress = [e.content for e in agent.store.events if e.kind == InputKind.PROCESS_PROGRESS]
    assert len(progress) == 2 and progress[-1].endswith("process complete")


async def test_download_and_restore(script, make_host, make_backend):
    backend = make_backend()
    script.on("decide", decide("memory"), decide("done"), decide("memory"))
    script.on(
        "capability:memory",
        remember(node_op("pref-thai", "Likes Thai")),
        remember(node_op("pref-new", "Something new")),
    )
    host = make_host(script, backend)
    await host.run("maya", InputEvent(InputKind.TEXT, "I love Thai"))

    download = json.loads(json.dumps(await host.export_state("maya")))  # survives a trip through a file
    assert download["format"] == "quintessa.agent-state" and download["version"] == 1
    assert download["user_id"] == "maya"

    await host.run("maya", InputEvent(InputKind.TEXT, "something new"))
    assert "pref-new" in (await host.agent("maya")).store.nodes

    await host.restore_state("maya", download)
    agent = await host.agent("maya")
    assert set(agent.store.nodes) == {"pref-thai"}
    assert (await backend.load("maya"))["memory"]["nodes"][0]["id"] == "pref-thai"

    await host.restore_state("maya-new-phone", download)
    assert set((await host.agent("maya-new-phone")).store.nodes) == {"pref-thai"}
    assert (await host.export_state("maya-new-phone"))["user_id"] == "maya-new-phone"


@pytest.mark.parametrize(
    "bad",
    [
        {"hello": "world"},
        {"format": "quintessa.agent-state", "version": 99, "memory": {}, "device": {}},
        {"format": "quintessa.agent-state", "version": 1, "memory": {"nodes": "?"}, "device": {}},
        {"format": "quintessa.agent-state", "version": 1, "memory": {"nodes": []}, "device": {}},
    ],
)
async def test_restore_rejects_bad_files_without_touching_state(script, make_host, make_backend, bad):
    script.on("decide", decide("memory"))
    script.on("capability:memory", remember(node_op("pref-thai", "Likes Thai")))
    backend = make_backend()
    host = make_host(script, backend)
    await host.run("maya", InputEvent(InputKind.TEXT, "I love Thai"))
    await host.save("maya")
    with pytest.raises(StateFormatError):
        await host.restore_state("maya", bad)
    assert set((await host.agent("maya")).store.nodes) == {"pref-thai"}
    assert [n["id"] for n in (await backend.load("maya"))["memory"]["nodes"]] == ["pref-thai"]


async def test_changes_are_saved_without_an_explicit_save(script, make_host):
    backend = InMemoryStateBackend()
    script.on("decide", decide("memory"))
    script.on("capability:memory", remember(node_op("pref-thai", "Likes Thai")))
    host = make_host(script, backend)
    await host.run("maya", InputEvent(InputKind.TEXT, "I love Thai"))
    await until(lambda: backend.records.get("maya", {}).get("memory", {}).get("nodes"))
    saved = backend.records["maya"]
    assert saved["memory"]["sessions"][0]["status"] == "complete"


async def test_clear_is_per_user_and_durable(script, make_host, make_backend):
    backend = make_backend()
    script.on("decide", decide("memory"), decide("done"), decide("memory"))
    script.on("capability:memory", remember(node_op("a", "A")), remember(node_op("b", "B")))
    host = make_host(script, backend)
    await host.run("maya", InputEvent(InputKind.TEXT, "a"))
    await host.run("tunde", InputEvent(InputKind.TEXT, "b"))
    await host.clear("maya")
    assert (await host.agent("maya")).store.nodes == {} and (await backend.load("maya"))["memory"]["nodes"] == []
    assert set((await host.agent("tunde")).store.nodes) == {"b"}
    await host.shutdown()
    assert [n["id"] for n in (await make_backend().load("tunde"))["memory"]["nodes"]] == ["b"]


async def test_answers_go_to_the_right_user(script, make_host):
    script.on("decide", decide("generative_ui"))
    script.on(
        "capability:generative_ui",
        {
            "prompt": "Which?",
            "purpose": "information",
            "context": "",
            "fields": [],
            "document_id": None,
            "section_id": None,
            "topic_id": None,
            "tool": None,
            "function": None,
        },
    )
    host = make_host(script, InMemoryStateBackend())
    session = await host.submit("maya", InputEvent(InputKind.TEXT, "x"))
    await until(lambda: session.status == SessionStatus.WAITING_FOR_USER)
    assert not await host.answer("tunde", UXResponse(session.pending_ux_id, {}))
    assert await host.answer("maya", UXResponse(session.pending_ux_id, {}))
    await (await host.agent("maya")).wait_idle()
    assert session.status == SessionStatus.COMPLETE
