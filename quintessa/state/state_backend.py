from __future__ import annotations

from typing import Any, Protocol


class StateBackend(Protocol):
    """Durable storage for per-user agent state. One record per user id."""

    async def load(self, user_id: str) -> dict[str, Any] | None: ...

    async def save(self, user_id: str, data: dict[str, Any]) -> None: ...

    async def delete(self, user_id: str) -> None: ...

    async def list_users(self) -> list[str]: ...
