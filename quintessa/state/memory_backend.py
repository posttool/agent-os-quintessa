from __future__ import annotations

import copy
from typing import Any


class InMemoryStateBackend:
    """Non-durable backend for tests and demos."""

    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.saves = 0

    async def load(self, user_id: str) -> dict[str, Any] | None:
        return copy.deepcopy(self.records.get(user_id))

    async def save(self, user_id: str, data: dict[str, Any]) -> None:
        self.saves += 1
        self.records[user_id] = copy.deepcopy(data)

    async def delete(self, user_id: str) -> None:
        self.records.pop(user_id, None)

    async def list_users(self) -> list[str]:
        return sorted(self.records)
