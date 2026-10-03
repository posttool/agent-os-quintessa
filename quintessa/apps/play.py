from __future__ import annotations

import asyncio
from typing import Any

from quintessa.apps.store import play_url
from quintessa.models import AppListing


class PlayStore:
    """Google Play search through the google-play-scraper library (no API
    key; it reads the public store pages). Needs network access to
    play.google.com."""

    name = "play"

    def __init__(self, *, lang: str = "en", country: str = "us"):
        self.lang = lang
        self.country = country

    async def search(self, query: str, limit: int = 8) -> list[AppListing]:
        from google_play_scraper import search

        results = await asyncio.to_thread(search, query, n_hits=limit, lang=self.lang, country=self.country)
        return [listing for r in results[:limit] if (listing := self.listing(r))]

    @staticmethod
    def listing(r: dict[str, Any]) -> AppListing | None:
        if not r.get("appId"):
            return None
        score = r.get("score")
        return AppListing(
            app_id=r["appId"],
            title=r.get("title") or r["appId"],
            store="play",
            developer=r.get("developer") or "",
            icon_url=r.get("icon") or "",
            category=r.get("genre") or "",
            rating=round(float(score), 1) if score else None,
            store_url=play_url(r["appId"]),
            summary=(r.get("description") or "")[:300],
        )
