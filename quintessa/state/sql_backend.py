from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import Boolean, Column, Index, Integer, MetaData, String, Table, Text, event, func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from quintessa.clock import now

log = logging.getLogger(__name__)

metadata = MetaData()
CHUNK = 500  # keys per IN (...) clause, well under every database's variable limit


@dataclass(frozen=True)
class Collection:
    """How one memory collection (a list in MemoryStore.to_data) maps to a
    table: its key and the columns pulled out of the JSON body for querying."""

    name: str
    key: Callable[[int, dict[str, Any]], str]
    columns: dict[str, Callable[[dict[str, Any]], Any]] = field(default_factory=dict)
    booleans: frozenset[str] = frozenset()


def _get(name: str) -> Callable[[dict[str, Any]], Any]:
    return lambda d: d.get(name)


COLLECTIONS = [
    Collection("nodes", lambda _, d: d["id"], {"type": _get("type"), "topic_id": _get("topic_id"), "updated_at": _get("updated_at")}),
    Collection("edges", lambda _, d: json.dumps([d["source_id"], d["target_id"], d["type"]]),
               {"source_id": _get("source_id"), "target_id": _get("target_id"), "type": _get("type")}),
    Collection("topics", lambda _, d: d["id"], {"archived": _get("archived"), "updated_at": _get("updated_at")},
               frozenset({"archived"})),
    Collection("documents", lambda _, d: d["id"],
               {"topic_id": _get("topic_id"), "status": _get("status"), "updated_at": _get("updated_at")}),
    Collection("tools", lambda _, d: d["name"],
               {"kind": _get("kind"), "binding": _get("binding"), "app_id": lambda d: (d.get("listing") or {}).get("app_id")}),
    Collection("permissions", lambda seq, _: str(seq), {"tool": _get("tool"), "function": _get("function"), "scope": _get("scope")}),
    Collection("subscriptions", lambda _, d: d["id"], {"archived": _get("archived")}, frozenset({"archived"})),
    Collection("events", lambda _, d: d["id"],
               {"kind": _get("kind"), "source": _get("source"), "occurred_at": _get("occurred_at")}),
    Collection("sessions", lambda _, d: d["id"],
               {"status": _get("status"), "started_at": _get("started_at"),
                "has_jev_decisions": lambda d: bool(d.get("shadow_decisions"))},
               frozenset({"has_jev_decisions"})),
]

users = Table(
    "users", metadata,
    Column("user_id", String, primary_key=True),
    Column("created_at", String, nullable=False),
    Column("saved_at", String),
    Column("device", Text, nullable=False),
    Column("preferences", Text),
    Column("persona", Text),
    Column("extra", Text, nullable=False),  # any other top-level snapshot keys (format, version, ...)
)


def _item_table(c: Collection) -> Table:
    extra = [Column(name, Boolean if name in c.booleans else String) for name in c.columns]
    return Table(
        c.name, metadata,
        Column("user_id", String, primary_key=True),
        Column("key", String, primary_key=True),
        Column("seq", Integer, nullable=False),
        Column("hash", String(32), nullable=False),
        Column("body", Text, nullable=False),
        *extra,
        Index(f"ix_{c.name}_user_seq", "user_id", "seq"),
        *[Index(f"ix_{c.name}_{name}", "user_id", name) for name in c.columns],
    )


TABLES = {c.name: _item_table(c) for c in COLLECTIONS}

schema_version = Table("schema_version", metadata, Column("version", Integer, nullable=False))


async def _create_tables(conn: AsyncConnection) -> None:
    await conn.run_sync(lambda sync: metadata.create_all(sync, tables=[users, *TABLES.values()]))


# Numbered schema steps. Add new ones at the end; never edit a released one.
MIGRATIONS: list[Callable[[AsyncConnection], Any]] = [_create_tables]

USER_KEYS = ("device", "preferences", "persona")


def database_url(url: str) -> str:
    """Accept plain URLs (sqlite:///x.db, postgresql://...) and pick the async driver."""
    for plain, driver in (("sqlite://", "sqlite+aiosqlite://"), ("postgresql://", "postgresql+asyncpg://"),
                          ("postgres://", "postgresql+asyncpg://")):
        if url.startswith(plain):
            return driver + url[len(plain):]
    return url


def _hash(body: str) -> str:
    return hashlib.blake2b(body.encode(), digest_size=16).hexdigest()


class SqlStateBackend:
    """Per-user agent state in a SQL database (SQLite by default, Postgres by
    URL). Every table is keyed by user id first. Each memory item is one row
    holding its JSON plus a few indexed columns; a save writes only the rows
    whose JSON changed and deletes rows for items that are gone, all in one
    transaction, so a crash leaves either the old state or the new one.

    `import_from`: a FileStateBackend folder whose users are copied in on
    first use (each file is renamed to .json.imported afterwards)."""

    def __init__(self, url: str, *, import_from: str | Path | None = None):
        self.url = database_url(url)
        self.import_from = Path(import_from) if import_from else None
        if self.url.startswith("sqlite+aiosqlite:///") and ":memory:" not in self.url:
            Path(self.url.removeprefix("sqlite+aiosqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        self.engine: AsyncEngine = create_async_engine(self.url)
        if self.engine.dialect.name == "sqlite":
            event.listen(self.engine.sync_engine, "connect", _sqlite_pragmas)
        self._ready = False
        self._init_lock = asyncio.Lock()
        self._user_locks: dict[str, asyncio.Lock] = {}
        # what is in the database, per user and collection: key -> (seq, hash)
        self._written: dict[str, dict[str, dict[str, tuple[int, str]]]] = {}

    # --- setup ----------------------------------------------------------------------

    async def _setup(self) -> None:
        if self._ready:
            return
        async with self._init_lock:
            if self._ready:
                return
            async with self.engine.begin() as conn:
                await conn.run_sync(lambda sync: schema_version.create(sync, checkfirst=True))
                version = (await conn.execute(select(schema_version.c.version))).scalar()
                if version is None:
                    await conn.execute(schema_version.insert().values(version=0))
                    version = 0
                for step in MIGRATIONS[version:]:
                    await step(conn)
                if version < len(MIGRATIONS):
                    await conn.execute(schema_version.update().values(version=len(MIGRATIONS)))
            if self.import_from is not None:
                await self._import_files(self.import_from)
            self._ready = True

    async def _import_files(self, folder: Path) -> None:
        for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
            try:
                data = json.loads(path.read_text())
                user_id = data["user_id"]
                async with self.engine.connect() as conn:
                    exists = (await conn.execute(select(users.c.user_id).where(users.c.user_id == user_id))).first()
                if exists is None:
                    await self._write(user_id, data)
                    log.info("imported agent state for %s from %s", user_id, path)
                path.rename(path.with_name(path.name + ".imported"))
            except Exception:
                log.exception("could not import agent state from %s; left in place", path)

    async def close(self) -> None:
        await self.engine.dispose()

    def _lock(self, user_id: str) -> asyncio.Lock:
        return self._user_locks.setdefault(user_id, asyncio.Lock())

    # --- StateBackend -----------------------------------------------------------------

    async def load(self, user_id: str) -> dict[str, Any] | None:
        await self._setup()
        async with self._lock(user_id), self.engine.connect() as conn:
            row = (await conn.execute(select(users).where(users.c.user_id == user_id))).mappings().first()
            if row is None:
                return None
            data: dict[str, Any] = {**json.loads(row["extra"]), "user_id": user_id}
            for name in USER_KEYS:
                if row[name] is not None:
                    data[name] = json.loads(row[name])
            memory, written = {}, {}
            for name, table in TABLES.items():
                rows = (await conn.execute(
                    select(table.c.key, table.c.seq, table.c.hash, table.c.body)
                    .where(table.c.user_id == user_id).order_by(table.c.seq)
                )).all()
                memory[name] = [json.loads(r.body) for r in rows]
                written[name] = {r.key: (r.seq, r.hash) for r in rows}
            data["memory"] = memory
            self._written[user_id] = written
            return data

    async def save(self, user_id: str, data: dict[str, Any]) -> None:
        await self._setup()
        await self._write(user_id, data)

    async def delete(self, user_id: str) -> None:
        await self._setup()
        async with self._lock(user_id), self.engine.begin() as conn:
            for table in (*TABLES.values(), users):
                await conn.execute(table.delete().where(table.c.user_id == user_id))
            self._written.pop(user_id, None)

    async def list_users(self) -> list[str]:
        await self._setup()
        async with self.engine.connect() as conn:
            return list((await conn.execute(select(users.c.user_id).order_by(users.c.user_id))).scalars())

    async def count_rows(self, user_id: str) -> dict[str, int]:
        """Rows stored per collection for one user (for diagnostics and tests)."""
        await self._setup()
        async with self.engine.connect() as conn:
            return {
                name: (await conn.execute(select(func.count()).select_from(t).where(t.c.user_id == user_id))).scalar_one()
                for name, t in TABLES.items()
            }

    # --- writing ----------------------------------------------------------------------

    async def _write(self, user_id: str, data: dict[str, Any]) -> None:
        memory = data["memory"]
        unknown = set(memory) - set(TABLES)
        if unknown:
            raise ValueError(f"memory has collections the database does not store: {sorted(unknown)}")
        async with self._lock(user_id):
            async with self.engine.begin() as conn:
                before = self._written.get(user_id)
                if before is None:
                    before = await self._read_written(conn, user_id)
                after: dict[str, dict[str, tuple[int, str]]] = {}
                for c in COLLECTIONS:
                    after[c.name] = await self._write_collection(conn, c, user_id, memory.get(c.name, []), before.get(c.name, {}))
                await self._write_user(conn, user_id, data)
            self._written[user_id] = after

    async def _read_written(self, conn: AsyncConnection, user_id: str) -> dict[str, dict[str, tuple[int, str]]]:
        written = {}
        for name, t in TABLES.items():
            rows = await conn.execute(select(t.c.key, t.c.seq, t.c.hash).where(t.c.user_id == user_id))
            written[name] = {r.key: (r.seq, r.hash) for r in rows}
        return written

    async def _write_collection(
        self, conn: AsyncConnection, c: Collection, user_id: str, items: list[dict[str, Any]], before: dict[str, tuple[int, str]]
    ) -> dict[str, tuple[int, str]]:
        table = TABLES[c.name]
        after: dict[str, tuple[int, str]] = {}
        changed: list[dict[str, Any]] = []
        for seq, item in enumerate(items):
            key = c.key(seq, item)
            body = json.dumps(item)
            state = (seq, _hash(body))
            after[key] = state
            if before.get(key) != state:
                columns = {name: get(item) for name, get in c.columns.items()}
                changed.append({"user_id": user_id, "key": key, "seq": seq, "hash": state[1], "body": body, **columns})
        stale = [k for k in before if k not in after] + [r["key"] for r in changed if r["key"] in before]
        for i in range(0, len(stale), CHUNK):
            await conn.execute(table.delete().where(table.c.user_id == user_id, table.c.key.in_(stale[i:i + CHUNK])))
        if changed:
            await conn.execute(table.insert(), changed)
        return after

    async def _write_user(self, conn: AsyncConnection, user_id: str, data: dict[str, Any]) -> None:
        skip = {"user_id", "memory", *USER_KEYS}
        values = {
            "saved_at": data.get("saved_at"),
            "device": json.dumps(data.get("device", {})),
            "preferences": None if data.get("preferences") is None else json.dumps(data["preferences"]),
            "persona": None if data.get("persona") is None else json.dumps(data["persona"]),
            "extra": json.dumps({k: v for k, v in data.items() if k not in skip}),
        }
        result = await conn.execute(users.update().where(users.c.user_id == user_id).values(**values))
        if result.rowcount == 0:
            await conn.execute(users.insert().values(user_id=user_id, created_at=now().isoformat(), **values))


def _sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()
