from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Preferences:
    """One user's settings for their agent. None means "use the platform
    default" (from the environment), so changing the environment still
    reaches users who never touched the setting.

    jev:        the master switch for every System One (Jev, gev) call
    jev_shadow: ask Jev for the next step beside the LLM (recorded, never followed)
    jev_filter: skip ambient events Jev says do not matter"""

    jev: bool | None = None
    jev_shadow: bool | None = None
    jev_filter: bool | None = None
