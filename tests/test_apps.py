import httpx
from conftest import decide
from test_tools import call

from quintessa.apps import FallbackAppStore, OfflineCatalog, app_store_from_env
from quintessa.apps.installer import install_app
from quintessa.apps.web import WebSearchAppStore
from quintessa.models import (
    AuthKind,
    AuthState,
    InputEvent,
    InputKind,
    OversightLevel,
    SessionStatus,
    ToolBinding,
    ToolKind,
)
from quintessa.state import InMemoryStateBackend
from quintessa.tools import runner


def manifest(name="opentable", auth="oauth"):
    return {
        "name": name,
        "description": "Find and book restaurant tables.",
        "grounding": "",
        "auth": auth,
        "functions": [
            {
                "name": "search",
                "description": "Find tables",
                "returns": "list",
                "oversight": "auto_from_memory",
                "long_running": False,
                "parameters": [{"name": "query", "type": "string", "description": "", "required": True}],
            },
            {
                "name": "book",
                "description": "Book a table",
                "returns": "confirmation",
                "oversight": "confirm_once",
                "long_running": True,
                "parameters": [{"name": "time", "type": "string", "description": "", "required": True}],
            },
        ],
    }


def search_plan(*queries, reuse=(), uninstall=()):
    return {"reuse": list(reuse), "app_queries": list(queries), "uninstall": list(uninstall), "notes": ""}


def choose(*app_ids):
    return {"install": [{"app_id": a, "reason": "best known"} for a in app_ids], "tools": [], "notes": ""}


async def test_offline_catalog_ranks_matching_apps_first():
    catalog = OfflineCatalog()
    results = await catalog.search("restaurant reservations")
    assert results[0].app_id in {"com.opentable", "com.resy.android"}
    assert (await catalog.search("ride"))[0].app_id in {"com.ubercab", "me.lyft.android"}
    assert (await catalog.search("opentable"))[0].app_id == "com.opentable"
    assert all(r.store_url.endswith(r.app_id) for r in results)
    assert await catalog.search("qqqq") == []


async def test_fallback_skips_a_store_that_fails():
    class Blocked:
        name = "play"

        async def search(self, query, limit=8):
            raise OSError("Tunnel connection failed: 403 Forbidden")

    store = FallbackAppStore([Blocked(), OfflineCatalog()])
    assert store.name == "play+offline"
    assert (await store.search("food delivery"))[0].store == "offline"


async def test_web_search_store_keeps_only_ids_seen_in_results(script, make_runtime):
    class FakeSearch:
        async def search(self, query):
            return "Resy https://play.google.com/store/apps/details?id=com.resy.android"

    script.on(
        "app_store:extract",
        {
            "apps": [
                {
                    "app_id": "com.resy.android",
                    "title": "Resy",
                    "developer": "Resy",
                    "category": "Food",
                    "summary": "Book",
                },
                {"app_id": "com.invented.app", "title": "Fake", "developer": "", "category": "", "summary": ""},
            ]
        },
    )
    runtime = make_runtime(script)
    store = WebSearchAppStore(FakeSearch(), runtime.llm)
    assert [listing.app_id for listing in await store.search("reservations")] == ["com.resy.android"]


def test_app_store_from_env(monkeypatch):
    monkeypatch.setenv("QUINTESSA_APP_STORE", "offline")
    assert app_store_from_env(None, None).name == "offline"
    monkeypatch.delenv("QUINTESSA_APP_STORE")
    assert app_store_from_env(None, None).name == "play+offline"


async def test_agent_installs_an_app_then_uses_it(script, make_runtime):
    script.on("decide", decide("tool_discovery", "find an app to book dinner"), decide("tool_use", "book"))
    script.on("capability:tool_discovery", search_plan("restaurant reservations"))
    script.on("capability:tool_discovery:choose", choose("com.opentable"))
    script.on("app_manifest:com.opentable", manifest())
    script.on("capability:tool_use", call("opentable", "search", {"query": "sushi for 2 at 7"}))
    script.on(
        "tool:opentable.search",
        {"status": "done", "result": "Nobu 7:00, Sushi Ran 7:15", "progress_stages": [], "pictures": []},
    )
    runtime = make_runtime(script)

    session = await runtime.run(InputEvent(InputKind.TEXT, "book sushi for two at 7"))

    tool = runtime.store.tools["opentable"]
    assert tool.kind == ToolKind.APP and tool.binding == ToolBinding.SIMULATED
    assert tool.listing.app_id == "com.opentable" and tool.listing.title == "OpenTable"
    assert tool.auth.kind == AuthKind.OAUTH and tool.auth.state == AuthState.SIMULATED
    assert tool.function("book").oversight == OversightLevel.CONFIRM_ONCE
    assert "OpenTable" in tool.grounding
    first = session.steps[0].output
    assert first["installed"] == ["opentable"]
    assert any(c["app_id"] == "com.opentable" for c in first["candidates"])
    assert session.steps[1].output["result"]["result"].startswith("Nobu")
    assert "opentable" in script.prompts["decide"][1]["memory"]["tools"][-1]["name"]


async def test_an_app_that_is_not_installed_cannot_be_called(script, make_runtime):
    """tool_use may only name installed tools, so a call to an app that was
    found but never installed is rejected before anything runs."""
    script.on("decide", decide("tool_use", "book"))
    script.on("capability:tool_use", call("opentable", "book", {"time": "7pm"}))
    runtime = make_runtime(script)
    session = await runtime.run(InputEvent(InputKind.TEXT, "book"))
    assert session.steps[0].error and "opentable" not in runtime.store.tools
    assert not script.prompts["tool:opentable.book"]


async def test_installing_twice_keeps_one_app(script, make_runtime):
    script.on("app_manifest:com.opentable", manifest())
    runtime = make_runtime(script)
    listing = (await runtime.apps.search("opentable"))[0]
    first = await install_app(runtime, listing)
    second = await install_app(runtime, listing)
    assert first is second and [t.name for t in runtime.store.tools.values() if t.kind == ToolKind.APP] == ["opentable"]


async def test_app_name_never_replaces_a_builtin(script, make_runtime):
    script.on("app_manifest:com.google.android.apps.maps", manifest(name="web"))
    runtime = make_runtime(script)
    listing = (await runtime.apps.search("google maps"))[0]
    tool = await install_app(runtime, listing)
    assert tool.name == "web_2" and runtime.store.tools["web"].kind == ToolKind.BUILTIN


async def test_agent_uninstalls_only_its_own_apps(script, make_runtime):
    script.on("app_manifest:com.opentable", manifest())
    script.on("app_manifest:com.ubercab", manifest(name="uber"))
    runtime = make_runtime(script)
    await install_app(runtime, (await runtime.apps.search("opentable"))[0], created_by="user")
    await install_app(runtime, (await runtime.apps.search("uber ride"))[0])
    script.on("decide", decide("tool_discovery", "clean up"))
    script.on("capability:tool_discovery", search_plan(uninstall=["opentable", "uber"]))
    session = await runtime.run(InputEvent(InputKind.TEXT, "tidy apps"))
    assert session.steps[0].output["uninstalled"] == ["uber"]
    assert "opentable" in runtime.store.tools and "uber" not in runtime.store.tools


async def test_installing_never_asks(script, make_runtime):
    """Installs happen in the step itself, even for a user whose saved
    preferences still carry the old ask_before_install setting."""
    from quintessa.models import Preferences
    from quintessa.serde import from_dict

    script.on("decide", decide("tool_discovery", "find a ride app"))
    script.on("capability:tool_discovery", search_plan("uber ride"))
    script.on("capability:tool_discovery:choose", choose("com.ubercab"))
    script.on("app_manifest:com.ubercab", manifest(name="uber"))
    runtime = make_runtime(script)
    runtime.preferences = from_dict(Preferences, {"ask_before_install": True})
    asked = []
    runtime.questions.on_question(asked.append)

    session = await runtime.run(InputEvent(InputKind.TEXT, "get me a ride"))
    assert not asked and runtime.store.tools["uber"].kind == ToolKind.APP
    assert session.status == SessionStatus.COMPLETE


def test_prompts_forbid_asking_about_installs():
    from quintessa.capabilities.loader import load_capabilities, load_prompt

    caps = load_capabilities()
    assert "Never ask the user whether to install an app" in load_prompt("controller")
    assert "Never to ask whether to install an app" in caps["generative_ui"].choose_when
    assert "Never ask permission to install an app" in caps["generative_ui"].instructions


async def test_simulated_app_needing_sign_in_asks_the_user(script, make_runtime):
    script.on("app_manifest:com.opentable", manifest())
    runtime = make_runtime(script)
    tool = await install_app(runtime, (await runtime.apps.search("opentable"))[0])
    tool.auth.state = AuthState.NEEDED
    result = await runner.run_tool(runtime, tool, tool.function("search"), {"query": "x"})
    assert result.status == "needs_user" and "Sign in to OpenTable" in result.result


async def test_installed_apps_are_per_user_and_survive_restart(script, make_host):
    backend = InMemoryStateBackend()
    script.on("app_manifest:com.opentable", manifest())
    host = make_host(script, backend)
    maya = await host.agent("maya")
    await install_app(maya, (await maya.apps.search("opentable"))[0])
    await host.shutdown()

    host2 = make_host(script, backend)
    restored = (await host2.agent("maya")).store.tools["opentable"]
    assert restored.kind == ToolKind.APP and restored.listing.app_id == "com.opentable"
    assert restored.auth.kind == AuthKind.OAUTH
    assert "opentable" not in (await host2.agent("tunde")).store.tools

    exported = await host2.export_state("maya")
    await host2.restore_state("lee", exported)
    assert (await host2.agent("lee")).store.tools["opentable"].listing.title == "OpenTable"


async def test_apps_api_search_install_uninstall(script, make_host):
    from quintessa.api.app import create_app

    script.on("app_manifest:com.dd.doordash", manifest(name="doordash"))
    host = make_host(script, InMemoryStateBackend())
    app = create_app(host)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as api:
        found = (await api.get("/api/apps/search?user=maya&q=food delivery")).json()
        doordash = next(a for a in found if a["app_id"] == "com.dd.doordash")
        assert doordash["installed_as"] is None
        r = await api.post("/api/apps/install?user=maya", json=doordash)
        assert r.status_code == 200 and r.json()["created_by"] == "user"
        found = (await api.get("/api/apps/search?user=maya&q=doordash")).json()
        assert found[0]["installed_as"] == "doordash"
        assert (
            await api.post("/api/tools?user=maya", json={"name": "doordash", "description": "x"})
        ).status_code == 400
        state = (await api.get("/api/state?user=maya")).json()
        assert state["apps"] == {"store": "offline"}
        assert (await api.delete("/api/apps/com.dd.doordash?user=maya")).status_code == 200
        assert (await api.delete("/api/apps/com.dd.doordash?user=maya")).status_code == 404
        assert "doordash" not in (await host.agent("maya")).store.tools


async def test_simulated_app_sees_its_earlier_calls(script, make_runtime):
    """The menu call gets the search results it returned before, so it can
    describe the same restaurant instead of inventing another one."""
    script.on("decide", decide("tool_use", "find thai"), decide("tool_use", "menu"))
    script.on("app_manifest:com.ubercab.eats", manifest(name="uber_eats"))
    script.on(
        "capability:tool_use",
        call("uber_eats", "search", {"query": "thai near me"}),
        call("uber_eats", "search", {"query": "Kin Khao menu"}),
    )
    script.on(
        "tool:uber_eats.search",
        {"status": "done", "result": "Kin Khao (store_77), Lers Ros (store_12)", "progress_stages": [], "pictures": []},
    )
    script.on(
        "tool:uber_eats.search",
        {"status": "done", "result": "Kin Khao menu: pad thai $16", "progress_stages": [], "pictures": []},
    )
    runtime = make_runtime(script)
    await install_app(runtime, (await runtime.apps.search("uber eats"))[0])

    await runtime.run(InputEvent(InputKind.TEXT, "order thai"))

    first, second = script.prompts["tool:uber_eats.search"]
    assert first["earlier_calls"] == [] and first["why_the_agent_is_calling"] == "test"
    assert second["earlier_calls"][0]["result"] == "Kin Khao (store_77), Lers Ros (store_12)"
    tool = runtime.store.tools["uber_eats"]
    assert [r.arguments["query"] for r in tool.history] == ["thai near me", "Kin Khao menu"]
    assert all("history" not in t for t in runtime.store.snapshot()["tools"])  # kept out of the agent's prompts


async def test_tool_history_is_capped_and_saved(script, make_runtime):
    script.on("app_manifest:com.opentable", manifest())
    runtime = make_runtime(script)
    tool = await install_app(runtime, (await runtime.apps.search("opentable"))[0])
    for i in range(runner.HISTORY_KEPT + 5):
        script.on(
            "tool:opentable.search", {"status": "done", "result": f"result {i}", "progress_stages": [], "pictures": []}
        )
        await runner.run_tool(runtime, tool, tool.function("search"), {"query": str(i)})
    assert len(tool.history) == runner.HISTORY_KEPT and tool.history[-1].result == f"result {runner.HISTORY_KEPT + 4}"
    assert len(script.prompts["tool:opentable.search"][-1]["earlier_calls"]) == runner.HISTORY_SHOWN
    restored = runtime.store.to_data()["tools"]
    assert next(t for t in restored if t["name"] == "opentable")["history"][-1]["arguments"] == {
        "query": str(runner.HISTORY_KEPT + 4)
    }


async def test_simulated_calls_fail_about_one_in_five(script, make_runtime, monkeypatch):
    """The outcome is drawn in code, and the model is only allowed the
    statuses for that outcome, so the rate holds whatever the model prefers."""
    monkeypatch.delenv("QUINTESSA_SIM_FAILURE_RATE")
    monkeypatch.setattr(runner, "_rng", __import__("random").Random(7))
    seen = []

    def answer(payload):
        failing = "realistic problem" in payload["instruction"]
        seen.append(failing)
        assert "oversight" not in payload["function"]  # the agent already handled approval
        return {"status": "failed" if failing else "done", "result": "ok", "progress_stages": [], "pictures": []}

    script.on("app_manifest:com.opentable", manifest())
    runtime = make_runtime(script)
    tool = await install_app(runtime, (await runtime.apps.search("opentable"))[0])
    for _ in range(500):
        script.on("tool:opentable.book", answer)
        await runner.run_tool(runtime, tool, tool.function("book"), {"time": ""})
    assert 0.15 < sum(seen) / len(seen) < 0.25


async def test_a_succeeding_call_cannot_report_failure(script, make_runtime):
    """With the outcome drawn as success, the schema only allows done or
    in_progress, so a refusal is rejected as invalid output."""
    import pytest

    from quintessa.llm import LLMError

    script.on("app_manifest:com.opentable", manifest())
    script.on(
        "tool:opentable.book", {"status": "failed", "result": "missing time", "progress_stages": [], "pictures": []}
    )
    runtime = make_runtime(script)
    tool = await install_app(runtime, (await runtime.apps.search("opentable"))[0])
    with pytest.raises(LLMError):
        await runner.run_tool(runtime, tool, tool.function("book"), {"time": ""})
