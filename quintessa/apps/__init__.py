"""App stores the agent discovers apps in, and installing apps as tools."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from quintessa.apps.fallback import FallbackAppStore
from quintessa.apps.offline import OfflineCatalog
from quintessa.apps.play import PlayStore
from quintessa.apps.store import AppStore
from quintessa.apps.web import WebSearchAppStore
from quintessa.tools.search import SearchBackend

if TYPE_CHECKING:
    from quintessa.llm import ResilientLLM

__all__ = ["AppStore", "FallbackAppStore", "OfflineCatalog", "PlayStore", "WebSearchAppStore", "app_store_from_env"]


def app_store_from_env(search: SearchBackend | None, llm: "ResilientLLM") -> AppStore:
    """QUINTESSA_APP_STORE: play, search, offline, or auto (the default):
    Play, then web search (when a search backend exists), then the bundled catalog."""
    choice = os.environ.get("QUINTESSA_APP_STORE", "auto").lower()
    if choice == "play":
        return PlayStore()
    if choice == "search" and search is not None:
        return WebSearchAppStore(search, llm)
    if choice == "offline":
        return OfflineCatalog()
    stores: list[AppStore] = [PlayStore()]
    if search is not None:
        stores.append(WebSearchAppStore(search, llm))
    stores.append(OfflineCatalog())
    return FallbackAppStore(stores)
