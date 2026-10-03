from __future__ import annotations

import json
from typing import TYPE_CHECKING

from quintessa.apps.store import play_url
from quintessa.llm import schema as s
from quintessa.models import AppListing
from quintessa.tools.search import SearchBackend

if TYPE_CHECKING:
    from quintessa.llm import ResilientLLM

LISTINGS_SCHEMA = s.obj(
    {
        "apps": s.array(
            s.obj(
                {
                    "app_id": s.string("Play package name from a play.google.com/store/apps/details?id= URL."),
                    "title": s.string(),
                    "developer": s.string(),
                    "category": s.string(),
                    "summary": s.string("One sentence on what the app does."),
                }
            )
        )
    }
)


class WebSearchAppStore:
    """Finds Play listings through web search when the store itself is out
    of reach, and has a model pull the listings out of the results. Only
    apps with a Play package id seen in the results are kept; no icons."""

    name = "search"

    def __init__(self, search: SearchBackend, llm: "ResilientLLM"):
        self.backend = search
        self.llm = llm

    async def search(self, query: str, limit: int = 8) -> list[AppListing]:
        found = await self.backend.search(
            f"Android apps on Google Play for: {query}. "
            "List each app's name, developer and its play.google.com/store/apps/details?id= URL."
        )
        result = await self.llm.generate_json(
            system="Extract Google Play app listings from these search results. Only include apps whose "
            "package id appears in a play.google.com URL in the text. Never invent ids.",
            prompt=json.dumps({"query": query, "search_results": found}),
            schema=LISTINGS_SCHEMA,
            purpose="app_store:extract",
        )
        listings = []
        for a in result.data["apps"]:
            if not a["app_id"] or a["app_id"] not in found:
                continue
            listings.append(AppListing(store=self.name, store_url=play_url(a["app_id"]), **a))
        return listings[:limit]
