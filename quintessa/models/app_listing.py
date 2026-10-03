from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AppListing:
    """An app as an app store describes it. `app_id` is the store's id
    (a Play package name such as com.opentable); `store` names the catalog
    the listing came from (play, search, offline)."""

    app_id: str
    title: str
    store: str = ""
    developer: str = ""
    icon_url: str = ""
    category: str = ""
    rating: float | None = None
    store_url: str = ""
    summary: str = ""
