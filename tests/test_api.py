import httpx
import pytest

from quintessa.api import create_app
from quintessa.api.model_settings import ModelSettings
from quintessa.llm import ModelRoute, ResilientLLM, ScriptedLLM
from quintessa.models import InputEvent, InputKind, SessionStatus
from quintessa.persona import AuraPersonaClient
from quintessa.state import InMemoryStateBackend

from conftest import decide, until
from test_ambient_and_persona import aura_transport
from test_memory import node_op


@pytest.fixture
def api(script, make_host):
    host = make_host(script, InMemoryStateBackend())
    persona = AuraPersonaClient("https://example.test/fn", httpx.AsyncClient(transport=aura_transport([])))
    built = []

    def factory(chain):
        built.append(chain)
        return ResilientLLM([ModelRoute(ScriptedLLM(script), c.split(":", 1)[1]) for c in chain.split(",")])

    app = create_app(host, settings=ModelSettings(chain=["scripted:test-model"]), llm_factory=factory, persona_client=persona)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    client.host, client.built = host, built
    return client


async def test_requests_need_a_user(api):
    assert (await api.get("/api/state")).status_code == 400
    assert (await api.get("/api/state", headers={"X-Quintessa-User": "maya"})).json()["user_id"] == "maya"


async def test_input_runs_for_that_user_only(api, script):
    script.on("decide", decide("memory"))
    script.on("capability:memory", {"summary": "ok", "operations": [node_op("pref-thai", "Likes Thai")]})
    r = await api.post("/api/input?user=maya", json={"content": "I love Thai"})
    session_id = r.json()["session_id"]
    agent = await api.host.agent("maya")
    await agent.wait_idle()

    maya = (await api.get("/api/state?user=maya")).json()
    tunde = (await api.get("/api/state?user=tunde")).json()
    assert [n["id"] for n in maya["memory"]["nodes"]] == ["pref-thai"]
    assert maya["memory"]["sessions"][0]["id"] == session_id
    assert tunde["memory"]["nodes"] == [] and tunde["memory"]["sessions"] == []


async def test_answering_a_question(api, script):
    script.on("decide", decide("generative_ui"))
    script.on("capability:generative_ui", {
        "prompt": "Which night?", "purpose": "disambiguation",
        "fields": [{"name": "night", "kind": "option", "label": "Night", "options": ["Tue", "Wed"]}],
        "document_id": None, "section_id": None, "tool": None, "function": None})
    await api.post("/api/input?user=maya", json={"content": "dinner"})
    agent = await api.host.agent("maya")
    await until(lambda: bool(agent.ux.pending))
    pending = (await api.get("/api/state?user=maya")).json()["pending_ux"]
    assert pending[0]["prompt"] == "Which night?"

    assert (await api.post(f"/api/ux/{pending[0]['id']}?user=tunde", json={"values": {}})).status_code == 404
    assert (await api.post(f"/api/ux/{pending[0]['id']}?user=maya", json={"values": {"night": "Wed"}})).status_code == 200
    await agent.wait_idle()
    session = next(iter(agent.store.sessions.values()))
    assert session.status == SessionStatus.COMPLETE and "Wed" in session.steps[0].summary


async def test_export_restore_and_clear(api, script):
    script.on("decide", decide("memory"))
    script.on("capability:memory", {"summary": "ok", "operations": [node_op("pref-thai", "Likes Thai")]})
    await api.post("/api/input?user=maya", json={"content": "I love Thai"})
    await (await api.host.agent("maya")).wait_idle()

    download = await api.get("/api/export?user=maya")
    assert "attachment" in download.headers["content-disposition"]
    assert (await api.post("/api/clear?user=maya")).status_code == 200
    assert (await api.get("/api/state?user=maya")).json()["memory"]["nodes"] == []

    assert (await api.post("/api/restore?user=maya", content=b"not json")).status_code == 400
    assert (await api.post("/api/restore?user=maya", json={"format": "nope"})).status_code == 400
    assert (await api.post("/api/restore?user=maya", content=download.content)).status_code == 200
    assert [n["id"] for n in (await api.get("/api/state?user=maya")).json()["memory"]["nodes"]] == ["pref-thai"]


async def test_tools_can_be_created_and_deleted_but_not_builtins(api):
    tool = {"name": "rides", "description": "Ride hailing", "kind": "llm",
            "functions": [{"name": "request_ride", "oversight": "always_ask", "long_running": True,
                           "parameters": [{"name": "to", "type": "string"}]}]}
    assert (await api.post("/api/tools?user=maya", json=tool)).status_code == 200
    tools = {t["name"]: t for t in (await api.get("/api/state?user=maya")).json()["memory"]["tools"]}
    assert tools["rides"]["functions"][0]["oversight"] == "always_ask" and tools["rides"]["created_by"] == "user"
    assert (await api.delete("/api/tools/device?user=maya")).status_code == 400
    assert (await api.post("/api/tools?user=maya", json={**tool, "name": "web"})).status_code == 400
    assert (await api.delete("/api/tools/rides?user=maya")).status_code == 200
    assert (await api.delete("/api/tools/rides?user=maya")).status_code == 404


async def test_ambient_sources(api, script):
    script.on("ambient:vibe", {"name": "oven", "kind": "sensor", "device": "oven", "sender": "",
                               "interval_seconds": 0, "events": ["preheated", "roast done"]})
    script.on("ambient:generate", {"sender": "Mom", "device": "phone", "events": ["call me"]})
    assert (await api.put("/api/ambient/enabled?user=maya", json={"enabled": False})).status_code == 200
    vibe = (await api.post("/api/ambient/sources/vibe?user=maya", json={"description": "a smart oven"})).json()
    templ = (await api.post("/api/ambient/sources/from-template?user=maya", json={"template": "sms", "count": 1})).json()
    assert (await api.post("/api/ambient/sources/from-template?user=maya", json={"template": "nope"})).status_code == 404
    state = (await api.get("/api/state?user=maya")).json()["ambient"]
    assert state["enabled"] is False
    sources = {s["id"]: s for s in state["sources"]}
    assert sources[vibe["id"]]["kind"] == "sensor" and sources[vibe["id"]]["interval_seconds"] == 1.0
    assert sources[templ["id"]]["sender"] == "Mom"

    assert (await api.patch(f"/api/ambient/sources/{vibe['id']}?user=maya", json={"speed": 4})).status_code == 200
    assert (await api.host.agent("maya")).ambient.sources[vibe["id"]].speed == 4
    assert (await api.delete(f"/api/ambient/sources/{vibe['id']}?user=maya")).status_code == 200
    custom = {"name": "texts", "kind": "message", "events": ["hi"], "interval_seconds": 0}
    assert (await api.post("/api/ambient/sources?user=maya", json=custom)).status_code == 200
    templates = (await api.get("/api/ambient/templates")).json()
    assert {t["name"] for t in templates} >= {"email", "sms", "home_security", "drive_to_office"}


async def test_persona_simulation_through_the_api(api):
    people = (await api.get("/api/personas")).json()
    assert people[0]["name"] == "Maya Okafor" and "raw" not in people[0]
    started = (await api.post("/api/persona/start?user=maya", json={"persona_id": "p_maya", "speed": 100000})).json()
    assert started["date"] == "2026-05-26"
    agent = await api.host.agent("maya")
    await until(lambda: len(agent.store.events) == 4)
    state = (await api.get("/api/state?user=maya")).json()
    assert state["persona"]["profile"]["name"] == "Maya Okafor" and state["persona"]["date"] == "2026-05-26"
    assert [e["kind"] for e in state["memory"]["events"]][1:] == [InputKind.LOCATION.value, "notification", "location"]
    await api.post("/api/persona/stop?user=maya")
    await api.post("/api/clear?user=maya")
    assert (await api.get("/api/state?user=maya")).json()["persona"] is None


async def test_model_settings_rebuild_the_chain(api, script):
    r = await api.put("/api/settings", json={"chain": ["scripted:fast", "scripted:older"], "retries": 1, "base_delay": 0.5})
    assert r.json()["chain"] == ["scripted:fast", "scripted:older"]
    assert [route.model for route in api.host.llm.routes] == ["fast", "older"]
    assert api.host.llm.retries == 1 and api.host.llm.base_delay == 0.5
    assert (await api.put("/api/settings", json={"chain": [" "]})).status_code == 400


async def test_model_settings_report_setup_errors(script, make_host):
    host = make_host(script, InMemoryStateBackend())

    def broken(chain):
        raise ValueError("unknown LLM provider 'nope'")

    app = create_app(host, llm_factory=broken)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    settings = (await client.put("/api/settings", json={"chain": ["nope:x"]})).json()
    assert "unknown LLM provider" in settings["status"]
    session = await host.run("maya", InputEvent(InputKind.TEXT, "hi"))
    assert session.status == SessionStatus.FAILED and "no model is configured" in session.steps[-1].error


async def test_watchers_hear_about_changes(api, script):
    agent = await api.host.agent("maya")
    heard = []
    agent.watchers.add(lambda: heard.append(1))
    await api.post("/api/tools?user=maya", json={"name": "x", "description": "x"})
    await api.put("/api/ambient/enabled?user=maya", json={"enabled": False})
    assert len(heard) >= 2


async def test_static_app_is_served(script, make_host, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>quintessa</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    app = create_app(make_host(script, InMemoryStateBackend()), static_dir=dist)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    assert (await client.get("/")).text == "<html>quintessa</html>"
    assert (await client.get("/memory")).text == "<html>quintessa</html>"
    assert (await client.get("/assets/app.js")).text == "console.log(1)"
    assert (await client.get("/../../etc/passwd")).text == "<html>quintessa</html>"


async def test_jev_preference_is_per_user_and_saved(api):
    r = await api.put("/api/preferences?user=maya", json={"jev": False})
    assert r.json()["jev"] is False and r.json()["available"] is False  # no Jev configured in tests
    assert (await api.get("/api/state?user=maya")).json()["jev"]["jev"] is False
    assert (await api.get("/api/state?user=tunde")).json()["jev"]["jev"] is True

    await api.host.save("maya")
    saved = await api.host.backend.load("maya")
    assert saved["preferences"] == {"jev": False, "jev_shadow": None, "jev_filter": None, "jev_drive": None}
    await api.post("/api/clear?user=maya")  # clearing memory keeps settings
    assert (await api.get("/api/state?user=maya")).json()["jev"]["jev"] is False
    r = await api.put("/api/preferences?user=maya", json={"jev": None})  # back to the platform default
    assert r.json()["jev"] is True


async def test_model_catalog_groups_claude_and_gemini(api):
    catalog = (await api.get("/api/models")).json()
    assert [p["provider"] for p in catalog] == ["claude", "gemini"]
    ids = [m["id"] for p in catalog for m in p["models"]]
    assert "claude:claude-opus-5-5" in ids and "gemini:gemini-3.8-flash" in ids
