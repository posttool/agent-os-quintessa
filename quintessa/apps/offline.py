from __future__ import annotations

import json
import re
from importlib import resources

from quintessa.apps.store import play_url
from quintessa.models import AppListing

_WORD = re.compile(r"[a-z0-9]+")
_STOP = {"a", "an", "and", "app", "apps", "for", "the", "to", "of", "or", "with", "my", "on", "in"}


def _words(text: str) -> set[str]:
    words = set(_WORD.findall(text.lower())) - _STOP
    return words | {w[:-1] for w in words if w.endswith("s") and len(w) > 3}


class OfflineCatalog:
    """A small bundled catalog of common apps, searched by word overlap.
    Works without any network; listings carry no icons."""

    name = "offline"

    def __init__(self, listings: list[AppListing] | None = None):
        if listings is None:
            data = json.loads(resources.files("quintessa.samples").joinpath("app_catalog.json").read_text())
            listings = [AppListing(store=self.name, store_url=play_url(a["app_id"]), **a) for a in data]
        self.listings = listings

    async def search(self, query: str, limit: int = 8) -> list[AppListing]:
        wanted = _words(query)
        scored = []
        for listing in self.listings:
            title = _words(listing.title)
            body = _words(f"{listing.developer} {listing.category} {listing.summary}")
            score = 3 * len(wanted & title) + len(wanted & body)
            if score:
                scored.append((score, listing))
        scored.sort(key=lambda pair: -pair[0])
        return [listing for _, listing in scored[:limit]]
