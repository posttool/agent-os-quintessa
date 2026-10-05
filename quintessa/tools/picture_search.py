"""Real pictures for the items a tool returns. An image the app passes
through is kept when it loads; otherwise the picture is looked up on the
web by a search query, and a picture nothing is found for keeps its drawn
illustration."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from quintessa import config
from quintessa.models import Picture, PictureKind

log = logging.getLogger(__name__)

USER_AGENT = "Quintessa/0.1 (https://github.com/posttool/agent-os-quintessa)"
LOOKUP_TIMEOUT = 6.0  # seconds; a slow lookup only costs the picture, never the call
CACHE_SIZE = 500


@dataclass
class FoundPicture:
    url: str
    width: int
    height: int
    page_url: str  # where the picture is published, for credit
    credit: str  # "Wikimedia Commons"


class PictureSearch(Protocol):
    async def find(self, query: str) -> FoundPicture | None: ...

    async def loads(self, url: str) -> bool: ...


class WebPictures:
    """Checks images apps pass through, and finds the rest with Wikimedia
    Commons file search: free to use, no key, every result published with
    its license on its file page."""

    API = "https://commons.wikimedia.org/w/api.php"
    WIDTH = 800  # the scaled copy to show
    MIN_SIDE = 320
    MIMES = ("image/jpeg", "image/png", "image/webp")

    def __init__(self, client: httpx.AsyncClient | None = None):
        self.client = client or httpx.AsyncClient(timeout=LOOKUP_TIMEOUT, headers={"User-Agent": USER_AGENT})
        self._cache: dict[str, FoundPicture | None] = {}

    async def find(self, query: str) -> FoundPicture | None:
        key = query.strip().lower()
        if key in self._cache:
            return self._cache[key]
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"{query} filetype:bitmap",
            "gsrnamespace": "6",
            "gsrlimit": "6",
            "prop": "imageinfo",
            "iiprop": "url|size|mime",
            "iiurlwidth": str(self.WIDTH),
        }
        response = await self.client.get(self.API, params=params)
        response.raise_for_status()
        pages = sorted((response.json().get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
        found = next((f for f in map(self._usable, pages) if f), None)
        if len(self._cache) >= CACHE_SIZE:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = found
        return found

    async def loads(self, url: str) -> bool:
        """The URL answers with an image."""
        if not url.startswith(("https://", "http://")):
            return False
        async with self.client.stream("GET", url, follow_redirects=True) as response:
            return response.is_success and response.headers.get("content-type", "").startswith("image/")

    def _usable(self, page: dict) -> FoundPicture | None:
        info = (page.get("imageinfo") or [{}])[0]
        if info.get("mime") not in self.MIMES or min(info.get("width", 0), info.get("height", 0)) < self.MIN_SIDE:
            return None
        url = info.get("thumburl") or info.get("url")
        if not url:
            return None
        return FoundPicture(
            url,
            info.get("thumbwidth") or info["width"],
            info.get("thumbheight") or info["height"],
            info.get("descriptionurl", ""),
            "Wikimedia Commons",
        )


async def find_real_pictures(search: PictureSearch | None, pictures: list[tuple[Picture, str]]) -> None:
    """Make each picture a real image, in place: the one the app passed
    through if it loads, else one found by its query. A lookup that fails or
    finds nothing leaves the picture without a url, to be drawn."""
    if search is None:
        return

    async def attempt(call, what: str):
        try:
            return await asyncio.wait_for(call, LOOKUP_TIMEOUT)
        except (TimeoutError, httpx.HTTPError, ValueError) as e:
            log.info("picture %s failed: %s", what, e)
            return None

    async def one(picture: Picture, query: str) -> None:
        if picture.url:
            if await attempt(search.loads(picture.url), f"check of {picture.url}"):
                return
            picture.url, picture.width, picture.height = "", 0, 0
        if not query.strip():
            return
        found = await attempt(search.find(query), f"lookup for {query!r}")
        if found is not None:
            picture.url, picture.width, picture.height = found.url, found.width, found.height
            picture.page_url, picture.credit = found.page_url, found.credit

    await asyncio.gather(*(one(p, q) for p, q in pictures))


IMAGE_KEYS = ("image", "photo", "picture", "thumbnail", "thumb", "img", "logo", "icon")
NAME_KEYS = ("name", "title", "label", "caption", "alt")
MAX_PASSED_THROUGH = 8


def pictures_in_json(text: str, source: str) -> list[Picture]:
    """Images a web API passed through in a JSON response: each object with
    an image URL under a key like `image` or `thumbnail_url`, named by its
    `name` or `title`."""
    try:
        data = json.loads(text)
    except ValueError:
        return []
    found: list[Picture] = []

    def walk(value) -> None:
        if len(found) >= MAX_PASSED_THROUGH:
            return
        if isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            picture = _picture_of(value, source)
            if picture is not None:
                found.append(picture)
            for item in value.values():
                walk(item)

    walk(data)
    return found


def _picture_of(item: dict, source: str) -> Picture | None:
    name = next((v for k, v in item.items() if k.lower() in NAME_KEYS and isinstance(v, str) and v.strip()), None)
    for key, value in item.items():
        if not any(word in key.lower() for word in IMAGE_KEYS):
            continue
        url = value.get("url") if isinstance(value, dict) else value
        if name and isinstance(url, str) and url.startswith(("https://", "http://")):
            lowered = key.lower()
            kind = (
                PictureKind.LOGO
                if "logo" in lowered or "icon" in lowered
                else PictureKind.THUMBNAIL
                if "thumb" in lowered
                else PictureKind.PHOTO
            )
            size = value if isinstance(value, dict) else item
            width, height = size.get("width"), size.get("height")
            return Picture(
                name.strip(),
                kind,
                url,
                width=width if isinstance(width, int) else 0,
                height=height if isinstance(height, int) else 0,
                source=source,
            )
    return None


def picture_search_from_env() -> PictureSearch | None:
    """QUINTESSA_PICTURE_SEARCH: wikimedia (default) or off."""
    return None if config.picture_search() == "off" else WebPictures()
