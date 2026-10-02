import asyncio

from quintessa.llm import FatalLLMError
from quintessa.models import InputEvent, InputKind, SessionStatus, UXResponse

from conftest import decide, until
from test_memory import doc_op, node_op, section_op, topic_op


def memory_answer(*ops, summary="saved"):
    return {"summary": summary, "operations": list(ops)}


async def test_trigger_to_memory_then_done(script, make_runtime):
    script.on("decide", decide("memory", "save Jane's dinner idea", "Saving"))
    script.on("capability:memory", memory_answer(node_op("person-jane", "Jane", "person"), topic_op("topic-dinner", "Dinner Plans")))
    runtime = make_runtime(script)
    islands = []
    runtime.device.listen(lambda kind, state: kind == "island" and islands.append(state["island"]["words"]))

    session = await runtime.run(InputEvent(InputKind.MESSAGE, "Jane: zuni on tuesday?", sender="Jane"))

    assert session.status == SessionStatus.COMPLETE
    assert [s.capability for s in session.steps] == ["memory"]
    assert session.steps[0].summary == "saved" and session.steps[0].model == "test-model"
    assert "topic-dinner" in runtime.store.topics
    assert runtime.store.nodes["person-jane"].source_event_ids == [session.trigger.id]
    assert islands == ["Saving", ""] and not runtime.device.state.island.active
    # the second decision saw the first step's result
    assert script.prompts["decide"][1]["steps_so_far"][0]["summary"] == "saved"
    assert script.prompts["capability:memory"][0]["focus"] == "save Jane's dinner idea"


async def test_disambiguation_pauses_and_returns_to_the_document(script, make_runtime):
    script.on("decide", decide("memory"), decide("generative_ui", "which day"), decide("memory", "record the day"))
    script.on(
        "capability:memory",
        memory_answer(topic_op("topic-dinner", "Dinner"), doc_op("doc-dinner", "topic-dinner"), section_op("sec-time", "doc-dinner")),
        lambda payload: memory_answer(summary=f"recorded {payload['steps_so_far'][1]['summary']}"),
    )
    script.on(
        "capability:generative_ui",
        {"prompt": "Which night works?", "purpose": "disambiguation",
         "fields": [{"name": "night", "kind": "option", "label": "Night", "options": ["Tuesday", "Wednesday"]}],
         "document_id": "doc-dinner", "section_id": "sec-time", "tool": None, "function": None},
    )
    runtime = make_runtime(script)
    session = runtime.submit(InputEvent(InputKind.TEXT, "plan dinner with Jane"))

    await until(lambda: session.status == SessionStatus.WAITING_FOR_USER)
    request = next(iter(runtime.ux.pending.values()))
    assert runtime.device.state.open_ux_ids == [request.id]
    assert runtime.device.state.island.words == "Waiting for you"

    assert runtime.answer(UXResponse(request.id, {"night": "Wednesday"}))
    await runtime.wait_idle()

    assert session.status == SessionStatus.COMPLETE
    assert "Wednesday" in session.steps[1].summary
    assert "Wednesday" in session.steps[2].summary
    assert runtime.device.state.open_ux_ids == []
    assert runtime.device.state.focused_document_id == "doc-dinner"
    assert runtime.on_screen()["section_ids"] == ["sec-time"]
    assert runtime.on_screen()["set_by"] == "agent"


async def test_loops_run_concurrently_over_shared_memory(script, make_runtime):
    script.on("decide", decide("generative_ui"), decide("memory"))
    script.on(
        "capability:generative_ui",
        {"prompt": "Color?", "purpose": "disambiguation", "fields": [{"name": "c", "kind": "option", "label": "", "options": ["red", "blue"]}],
         "document_id": None, "section_id": None, "tool": None, "function": None},
    )
    script.on("capability:memory", memory_answer(node_op("pref-color", "Unknown color preference")))
    runtime = make_runtime(script)

    waiting = runtime.submit(InputEvent(InputKind.TEXT, "buy the sofa"))
    await until(lambda: waiting.status == SessionStatus.WAITING_FOR_USER)
    other = runtime.submit(InputEvent(InputKind.LOCATION, "home"))
    await until(lambda: other.status == SessionStatus.COMPLETE)

    assert waiting.status == SessionStatus.WAITING_FOR_USER
    assert "pref-color" in runtime.store.nodes
    runtime.answer(UXResponse(waiting.pending_ux_id, {"c": "blue"}))
    await runtime.wait_idle()
    assert waiting.status == SessionStatus.COMPLETE


async def test_llm_outage_fails_the_session_with_a_trace(script, make_runtime):
    script.on("decide", FatalLLMError("model not found"))
    runtime = make_runtime(script)
    session = await runtime.run(InputEvent(InputKind.TEXT, "hello"))
    assert session.status == SessionStatus.FAILED
    assert "model not found" in session.steps[-1].error
    assert not runtime.device.state.island.active


async def test_max_steps_bounds_the_chain(script, make_runtime):
    script.on("decide", *[decide("memory")] * 5)
    script.on("capability:memory", *[memory_answer()] * 5)
    runtime = make_runtime(script, max_steps=3)
    session = await runtime.run(InputEvent(InputKind.TEXT, "loop forever"))
    assert len(session.steps) == 3 and session.status == SessionStatus.COMPLETE


async def test_clear_resets_memory_traces_and_device(script, make_runtime):
    script.on("decide", decide("generative_ui"))
    script.on(
        "capability:generative_ui",
        {"prompt": "?", "purpose": "information", "fields": [], "document_id": None, "section_id": None, "tool": None, "function": None},
    )
    runtime = make_runtime(script)
    session = runtime.submit(InputEvent(InputKind.TEXT, "x"))
    await until(lambda: session.status == SessionStatus.WAITING_FOR_USER)
    await runtime.clear()
    assert runtime.store.sessions == {} and runtime.store.events == [] and runtime.ux.pending == {}
    assert runtime.device.state.open_ux_ids == []
    assert set(runtime.store.tools) == {"web", "device"}
    await asyncio.sleep(0)
