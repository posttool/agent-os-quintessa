from __future__ import annotations

from dataclasses import fields
from typing import Any

from quintessa.decide.ambient_filter import AmbientFilter
from quintessa.decide.card_scorer import CardScorer
from quintessa.decide.next_step import NextStepDecider
from quintessa.models import Preferences


class JevSwitches:
    """The Jev parts configured on this platform, and which of them one user
    has on. A part exists only when a Jev key is set; the user's preferences
    switch it on or off, and a preference the user never set falls back to
    the platform default."""

    def __init__(
        self,
        next_step: NextStepDecider | None = None,
        ambient_filter: AmbientFilter | None = None,
        card_scorer: CardScorer | None = None,
        *,
        shadow_default: bool = True,
        filter_default: bool = True,
    ):
        self.next_step = next_step  # picks the next step, beside the LLM (shadow) or instead of it (drive)
        self.ambient_filter = ambient_filter  # skips ambient events that do not matter
        self.card_scorer = card_scorer  # scores cards' urgency, context fit and person
        self.defaults = Preferences(
            jev=True, jev_shadow=shadow_default, jev_filter=filter_default, jev_drive=False, jev_rank=True
        )

    def setting(self, preferences: Preferences, name: str) -> bool:
        value = getattr(preferences, name)
        return getattr(self.defaults, name) if value is None else value

    def _on(self, preferences: Preferences, name: str) -> bool:
        return self.setting(preferences, "jev") and self.setting(preferences, name)

    def shadow(self, preferences: Preferences) -> NextStepDecider | None:
        """Jev asked beside the LLM at each decision."""
        return self.next_step if self._on(preferences, "jev_shadow") else None

    def driver(self, preferences: Preferences) -> NextStepDecider | None:
        """Jev picking the next step instead of the LLM."""
        return self.next_step if self._on(preferences, "jev_drive") else None

    def active_ambient_filter(self, preferences: Preferences) -> AmbientFilter | None:
        return self.ambient_filter if self._on(preferences, "jev_filter") else None

    def active_card_scorer(self, preferences: Preferences) -> CardScorer | None:
        return self.card_scorer if self._on(preferences, "jev_rank") else None

    def status(self, preferences: Preferences) -> dict[str, Any]:
        decider = self.next_step or self.ambient_filter or self.card_scorer
        return {
            "available": decider is not None,
            "model": decider.client.label if decider else "",
            "threshold": self.ambient_filter.threshold if self.ambient_filter else None,
            **{f.name: self.setting(preferences, f.name) for f in fields(Preferences)},
        }
