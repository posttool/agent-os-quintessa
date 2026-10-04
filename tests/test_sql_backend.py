import json

import httpx
import pytest
from conftest import decide
from sqlalchemy import event
from test_host import remember
from test_memory import node_op
from test_tools import mock_http

from quintessa.memory import MemoryStore
from quintessa.models import InputEvent, InputKind
from quintessa.state import FileStateBackend, user_folder_name
from quintessa.state.sql_backend import TABLES, database_url
from quintessa.tools.builtin import BUILTIN_IMPLEMENTATIONS


def snapshot(user_id, nodes=(), events=(), **extra):
    memory = {name: [] for name in TABLES}
    memory["nodes"] = [{"id": n, "type": "fact", "title": n.upper()} for n in nodes]
    memory["events"] = [{"id": e, "kind": "text", "content": e} for e in events]
    return {
        "format": "quintessa.agent-state",
        "version": 1,
        "user_id": user_id,
        "saved_at": "now",
        "memory": memory,
        "device": {"brief": []},
        "preferences": {"jev": None},
        **extra,
    }


def count_inserted_rows(backend):
    counts = {"rows": 0}

    def before(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO") and not statement.startswith("INSERT INTO users"):
            counts["rows"] += len(parameters) if executemany else 1

    event.listen(backend.engine.sync_engine, "before_cursor_execute", before)
    return counts


def test_every_memory_collection_has_a_table():
    assert set(MemoryStore().to_data()) == set(TABLES)


def test_plain_urls_get_an_async_driver():
    assert database_url("sqlite:///data/q.db") == "sqlite+aiosqlite:///data/q.db"
    assert database_url("postgresql://u@h/db") == "postgresql+asyncpg://u@h/db"
    assert database_url("sqlite+aiosqlite:///x.db") == "sqlite+aiosqlite:///x.db"


async def test_round_trip_keeps_order_and_unknown_keys(open_sql):
    backend = open_sql()
    data = snapshot("maya", nodes=["b", "a", "c"], events=["e1", "e2"], persona={"persona_id": "p"}, later_key=[1])
    await backend.save("maya", data)
    assert await open_sql().load("maya") == data
    assert await backend.load("nobody") is None


async def test_saves_write_only_what_changed(open_sql):
    backend = open_sql()
    await backend.save("maya", snapshot("maya", nodes=["a", "b"], events=[f"e{i}" for i in range(50)]))
    counts = count_inserted_rows(backend)

    data = snapshot("maya", nodes=["a", "b"], events=[f"e{i}" for i in range(51)])
    data["memory"]["nodes"][1]["title"] = "changed"
    await backend.save("maya", data)
    assert counts["rows"] == 2  # node b and event e50

    await backend.save("maya", snapshot("maya", nodes=["b"], events=[]))
    assert (await backend.count_rows("maya"))["events"] == 0
    assert [n["title"] for n in (await backend.load("maya"))["memory"]["nodes"]] == ["B"]


async def test_users_never_see_each_others_rows(open_sql):
    backend = open_sql()
    await backend.save("maya", snapshot("maya", nodes=["same-id"]))
    await backend.save("tunde", snapshot("tunde", nodes=["same-id", "other"]))
    await backend.save("maya", snapshot("maya", nodes=[]))
    assert len((await backend.load("tunde"))["memory"]["nodes"]) == 2
    await backend.delete("tunde")
    assert await backend.list_users() == ["maya"]
    assert await backend.load("tunde") is None


async def test_a_failed_save_leaves_the_previous_state(open_sql, monkeypatch):
    backend = open_sql()
    await backend.save("maya", snapshot("maya", nodes=["a"]))

    async def broken(*_):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(backend, "_write_user", broken)
    with pytest.raises(RuntimeError):
        await backend.save("maya", snapshot("maya", nodes=["x", "y"]))
    monkeypatch.undo()
    assert [n["id"] for n in (await open_sql().load("maya"))["memory"]["nodes"]] == ["a"]
    await backend.save("maya", snapshot("maya", nodes=["x"]))  # the change cache was not advanced
    assert [n["id"] for n in (await open_sql().load("maya"))["memory"]["nodes"]] == ["x"]


async def test_old_state_files_are_imported_once(open_sql, tmp_path):
    files = FileStateBackend(tmp_path / "agents")
    await files.save("maya", snapshot("maya", nodes=["from-file"]))
    (tmp_path / "agents" / "broken.json").write_text("{nope")

    backend = open_sql(import_from=tmp_path / "agents")
    assert await backend.list_users() == ["maya"]
    assert (await backend.load("maya"))["memory"]["nodes"][0]["id"] == "from-file"
    assert not files.path_for("maya").exists()
    assert files.path_for("maya").with_name(files.path_for("maya").name + ".imported").exists()
    assert (tmp_path / "agents" / "broken.json").exists()  # left for a person to look at

    await files.save("maya", snapshot("maya", nodes=["stale"]))  # a user already in the database is not overwritten
    assert (await open_sql(import_from=tmp_path / "agents").load("maya"))["memory"]["nodes"][0]["id"] == "from-file"


async def test_host_runs_save_through_the_database(script, make_host, open_sql):
    script.on("decide", decide("memory"))
    script.on("capability:memory", remember(node_op("pref-thai", "Likes Thai")))
    backend = open_sql()
    host = make_host(script, backend)
    await host.run("maya", InputEvent(InputKind.TEXT, "I love Thai"))
    await host.save("maya")
    assert await backend.count_rows("maya") == {
        **{name: 0 for name in TABLES},
        "nodes": 1,
        "tools": 2,
        "events": 1,
        "sessions": 1,
    }
    stored = json.loads(json.dumps(await backend.load("maya")))
    assert stored["memory"]["sessions"][0]["status"] == "complete"


async def test_downloads_are_kept_per_user(make_runtime, script, monkeypatch, tmp_path):
    mock_http(monkeypatch, lambda request: httpx.Response(200, content=b"hello"))
    download = BUILTIN_IMPLEMENTATIONS[("web", "download")]
    for user in ("maya", "tunde"):
        await download({"url": "https://example.test/menu.pdf"}, make_runtime(script, user_id=user))
    for user in ("maya", "tunde"):
        assert (tmp_path / "downloads" / user_folder_name(user) / "menu.pdf").read_bytes() == b"hello"
    assert not (tmp_path / "downloads" / "menu.pdf").exists()
