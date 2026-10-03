from __future__ import annotations

from typing import Protocol

from quintessa.models import AppListing


class AppStore(Protocol):
    """Somewhere the agent can find apps to install."""

    name: str

    async def search(self, query: str, limit: int = 8) -> list[AppListing]: ...


def play_url(app_id: str) -> str:
    return f"https://play.google.com/store/apps/details?id={app_id}"
