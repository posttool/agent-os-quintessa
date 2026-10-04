import json
from pathlib import Path

import httpx
from conftest import no_sleep, until

from quintessa.ambient import ambient_templates, source_from_template
from quintessa.models import AmbientSource, InputKind, SessionStatus
from quintessa.persona import AuraPersonaClient, PersonaSimulation

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "aura_persona.json").read_text())


def aura_transport(calls):
    def handler(request: httpx.Request) -> httpx.Response:
        function = request.url.path.rsplit("/", 1)[-1]
        data = json.loads(request.content)["data"]
        calls.append((function, data))
        result = {
            "listPersona": [FIXTURE["persona"]],
            "getPersona": FIXTURE["persona"],
            "listDaysForPersona": FIXTURE["days"],
            "listObservations": FIXTURE["observations"],
        }[function]
        return httpx.Response(200, json={"result": result})

    return httpx.MockTransport(handler)


async def test_aura_client_uses_callable_protocol():
    calls = []
    client = AuraPersonaClient("https://example.test/fn", httpx.AsyncClient(transport=aura_transport(calls)))
    personas = await client.list_personas(limit=5)
    observations = await client.list_observations("p_maya", "2026-05-26")
    assert personas[0].name == "Maya Okafor" and personas[0].apps[0] == "Gmail"
    assert observations[1].sender_app == "WhatsApp" and observations[1].sender == "Jane"
    assert calls == [("listPersona", {"limit": 5}), ("listObservations", {"id": "p_maya", "date": "2026-05-26"})]


async def test_persona_day_replays_into_the_runtime(script, make_runtime):
    runtime = make_runtime(script)
    runtime.store.put_tool(runtime.store.tools["web"])  # something to clear
    client = AuraPersonaClient("https://example.test/fn", httpx.AsyncClient(transport=aura_transport([])))
    delays = []

    async def sleep(d):
        delays.append(d)

    sim = PersonaSimulation(runtime, client, speed=60, max_gap=30, sleep=sleep)
    persona = await sim.start("p_maya")
    await sim.wait()
    await runtime.wait_idle()

    assert persona.id == "p_maya"
    events = runtime.store.events
    assert [e.kind for e in events] == [InputKind.TEXT, InputKind.LOCATION, InputKind.NOTIFICATION, InputKind.LOCATION]
    assert "Maya Okafor" in events[0].content
    assert events[2].content == "[2026-05-26 07:52:40] notification from WhatsApp: zuni on tuesday?"
    assert events[2].sender == "Jane" and events[3].device == "watch"
    assert delays == [7.4666666666666666, 30]
    assert all(s.status == SessionStatus.COMPLETE for s in runtime.store.sessions.values())


async def test_ambient_source_emits_at_its_rate(script, make_runtime):
    runtime = make_runtime(script)
    delays = []

    async def sleep(d):
        delays.append(d)
        await no_sleep(d)

    runtime.ambient._sleep = sleep
    runtime.ambient.add_source(
        AmbientSource("sms", InputKind.MESSAGE, ["hey", "you there?"], interval_seconds=10, speed=2)
    )
    await until(lambda: len(runtime.store.events) == 2)
    await runtime.wait_idle()
    assert [e.content for e in runtime.store.events] == ["hey", "you there?"]
    assert runtime.store.events[0].source == "ambient:sms"
    assert delays == [5.0, 5.0]


async def test_global_emission_switch(script, make_runtime):
    runtime = make_runtime(script)
    runtime.ambient.enabled = False
    runtime.ambient.add_source(AmbientSource("email", InputKind.MESSAGE, ["a"], interval_seconds=0))
    for _ in range(5):
        await no_sleep(0)
    assert runtime.store.events == []


async def test_templates_generate_grounded_sources(script, make_runtime):
    script.on("ambient:generate", {"sender": "Mom", "device": "phone", "events": ["Call me", "Dinner Sunday?"]})
    runtime = make_runtime(script)
    template = next(t for t in ambient_templates() if t["name"] == "sms")
    source = await source_from_template(runtime.llm, template, FIXTURE["persona"], count=2)
    assert source.kind == InputKind.MESSAGE and source.events == ["Call me", "Dinner Sunday?"]
    assert script.prompts["ambient:generate"][0]["persona"]["name"] == "Maya Okafor"
