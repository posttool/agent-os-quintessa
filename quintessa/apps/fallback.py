from __future__ import annotations

import logging

from quintessa.apps.store import AppStore
from quintessa.models import AppListing

log = logging.getLogger(__name__)


class FallbackAppStore:
    """Tries each store in order and returns the first non-empty answer.
    A store that errors (Play blocked by a proxy, say) is skipped."""

    def __init__(self, stores: list[AppStore]):
        self.stores = stores
        self.name = "+".join(store.name for store in stores)

    async def search(self, query: str, limit: int = 8) -> list[AppListing]:
        for store in self.stores:
            try:
                listings = await store.search(query, limit)
            except Exception as e:  # any failure means: try the next store
                log.warning("app store %s failed for %r: %s", store.name, query, e)
                continue
            if listings:
                return listings
        return []
