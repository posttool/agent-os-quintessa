from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from quintessa.clock import now
from quintessa.device import salience
from quintessa.device.card import Card
from quintessa.device.device_state import DeviceState
from quintessa.device.discovery_item import DiscoveryItem
from quintessa.device.document_focus import FOCUSED, DocumentFocus, FocusSource
from quintessa.device.salience import Suppression
from quintessa.device.stashed_question import StashedQuestion
from quintessa.serde import to_dict

Listener = Callable[[str, dict[str, Any]], None]


class DeviceSurface:
    """The device the agent inhabits. The device tool and the loop write here;
    a skin (the web app's phone panel, glasses, a watch) listens and draws."""

    def __init__(self) -> None:
        self.state = DeviceState()
        self._listeners: list[Listener] = []
        self._active_sessions: dict[str, str] = {}

    def listen(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def _emit(self, kind: str) -> None:
        payload = to_dict(self.state)
        for listener in self._listeners:
            listener(kind, payload)

    def load_state(self, state: DeviceState) -> None:
        self.state = state
        self._active_sessions.clear()
        self._emit("loaded")

    def reset(self) -> None:
        self.state = DeviceState()
        self._active_sessions.clear()
        self._emit("reset")

    def session_activity(self, session_id: str, words: str | None) -> None:
        """Island shows the latest activity of any running session."""
        if words:
            self._active_sessions[session_id] = words
        else:
            self._active_sessions.pop(session_id, None)
        latest = list(self._active_sessions.values())
        self.state.island.active = bool(latest)
        self.state.island.words = latest[-1] if latest else ""
        self._emit("island")

    def set_brief(self, cards: list[Card]) -> None:
        """Replace the brief. A card for a topic already in the brief takes
        over that card's id, so a sheet open on it follows the new text."""
        old = self.state.brief
        for card in cards:
            match = _match(old, card)
            if match is not None:
                card.id, card.created_at = match.id, match.created_at
        self.state.brief = cards
        self._drop_snoozed(cards)
        self._changed_brief()

    def put_brief(self, card: Card) -> Card | None:
        """Add a card, or replace the one with its id or its topic: a topic has
        one card, never a stack. Returns the card it replaced."""
        replaced = self._put(card)
        self._drop_snoozed([card])
        self._changed_brief()
        return replaced

    def _put(self, card: Card) -> Card | None:
        brief = self.state.brief
        old = _match(brief, card)
        if old is None:
            brief.append(card)
            return None
        card.id, card.created_at = old.id, old.created_at
        if card is not old and card.opened_at is None:
            card.opened_at = old.opened_at
        brief[brief.index(old)] = card
        return old

    def _drop_snoozed(self, cards: list[Card]) -> None:
        """A new card on a snoozed card's topic replaces it; the snooze still
        counts against the topic as a suppression."""
        self.state.snoozed = [s for s in self.state.snoozed if _match(cards, s) is None]

    def remove_cards(self, card_ids: list[str]) -> list[Card]:
        removed = [b for b in self.state.brief if b.id in card_ids]
        if removed:
            self.state.brief = [b for b in self.state.brief if b.id not in card_ids]
            self._changed_brief()
        return removed

    def prune_brief(self, at: datetime) -> list[Card]:
        """Drop cards whose time has passed ("Leave by 3pm" at 3:05), bring
        back snoozed cards whose snooze is over, and re-rank: time moves
        proximity and suppression even when no card changed."""
        due = [s for s in self.state.snoozed if s.snoozed_until is None or s.snoozed_until <= at]
        if due:
            self.state.snoozed = [s for s in self.state.snoozed if s not in due]
            for card in due:
                card.snoozed_until = None
                if not card.expired(at):
                    self._put(card)
        removed = self.remove_cards([b.id for b in self.state.brief if b.expired(at)])
        if due and not removed:
            self._changed_brief(at)
        else:
            self.rank_brief(at)
        return removed

    def rank_brief(self, at: datetime) -> None:
        """Order the brief by salience, highest first."""
        for card in self.state.brief:
            s = card.salience
            s.proximity = round(salience.proximity(card.due_at, at), 4)
            s.suppression = round(
                salience.suppression(
                    salience.card_key(card.topic_id, card.text),
                    card.opened_at,
                    card.updated_at,
                    self.state.suppressions,
                    at,
                ),
                4,
            )
            s.score = salience.score(s, card.urgency)
        self.state.brief.sort(key=lambda b: b.salience.score, reverse=True)

    def brief_scores_changed(self) -> None:
        """Scores changed outside the device (Jev scored the cards)."""
        self._changed_brief()

    def _changed_brief(self, at: datetime | None = None) -> None:
        self.rank_brief(at or now())
        self._emit("brief")

    def open_card(self, card_id: str) -> bool:
        """The user opened a card: it is not being ignored."""
        card = next((b for b in self.state.brief if b.id == card_id), None)
        if card is None:
            return False
        card.opened_at = now()
        self._changed_brief()
        return True

    def dismiss_card(self, card_id: str) -> Card | None:
        """The user swiped a card away. It leaves the brief, and its topic
        ranks lower for a while if the agent writes about it again."""
        card = next((b for b in self.state.brief if b.id == card_id), None)
        if card is None:
            return None
        self.state.suppressions.append(
            Suppression(salience.card_key(card.topic_id, card.text), salience.SuppressionKind.DISMISSED)
        )
        self._trim_suppressions()
        self.remove_cards([card.id])
        return card

    def snooze_card(self, card_id: str, until: datetime) -> Card | None:
        """ "Not now": the card leaves the brief until `until`, then comes
        back ranked a little lower."""
        card = next((b for b in self.state.brief if b.id == card_id), None)
        if card is None:
            return None
        card.snoozed_until = until
        self.state.snoozed.append(card)
        self.state.suppressions.append(
            Suppression(salience.card_key(card.topic_id, card.text), salience.SuppressionKind.SNOOZED)
        )
        self._trim_suppressions()
        self.remove_cards([card.id])
        return card

    def _trim_suppressions(self, keep: int = 200) -> None:
        self.state.suppressions = self.state.suppressions[-keep:]

    def show_question(self, question_id: str) -> None:
        self.state.open_question_ids.append(question_id)
        self._emit("question_open")

    def close_question(self, question_id: str, document_id: str | None, section_id: str | None) -> None:
        if question_id in self.state.open_question_ids:
            self.state.open_question_ids.remove(question_id)
        self.state.stashed = [q for q in self.state.stashed if q.question_id != question_id]
        if document_id:
            self.show_document(document_id, [section_id] if section_id else [])
        self._emit("question_closed")

    def stash(self, question_id: str, topic_id: str | None) -> None:
        """Put a waiting question aside: still unanswered, out of the stack."""
        if not self.is_stashed(question_id):
            self.state.stashed.append(StashedQuestion(question_id, topic_id))
            self._emit("stash")

    def unstash(self, question_ids: list[str]) -> list[str]:
        """Back to the needs-you stack. Returns the ids that were stashed."""
        back = [q.question_id for q in self.state.stashed if q.question_id in question_ids]
        if back:
            self.state.stashed = [q for q in self.state.stashed if q.question_id not in back]
            self._emit("stash")
        return back

    def is_stashed(self, question_id: str) -> bool:
        return any(q.question_id == question_id for q in self.state.stashed)

    def prune_stash(self, waiting: set[str], topic_changed: Callable[[str, datetime], bool]) -> list[str]:
        """Forget stashed questions nobody waits on any more, and bring back
        those whose topic changed after they were stashed: that is when they
        may matter again. Returns the ids brought back."""
        self.state.stashed = [q for q in self.state.stashed if q.question_id in waiting]
        return self.unstash(
            [q.question_id for q in self.state.stashed if q.topic_id and topic_changed(q.topic_id, q.stashed_at)]
        )

    def show_document(
        self,
        document_id: str,
        section_ids: list[str] | None = None,
        mode: str = FOCUSED,
        reason: str = "",
        set_by: FocusSource = FocusSource.AGENT,
    ) -> None:
        """Open a document in Spaces with these sections expanded (none: let
        the focus rule pick), or the whole document when mode is "full"."""
        if document_id not in self.state.space_document_ids:
            self.state.space_document_ids.append(document_id)
        self.state.focused_document_id = document_id
        self.state.focus[document_id] = DocumentFocus(document_id, list(section_ids or []), mode, reason, set_by)
        self._emit("space")

    def clear_focus(self, document_id: str) -> None:
        self.state.focus.pop(document_id, None)
        self._emit("space")

    def pin_focus(self, focus: DocumentFocus) -> None:
        """Keep a focus without changing which document is open."""
        self.state.focus[focus.document_id] = focus
        self._emit("space")

    def add_discovery(self, item: DiscoveryItem) -> None:
        self.state.discovery.append(item)
        self._emit("discovery")

    def notify(self, text: str) -> None:
        self.state.notifications.append(text)
        self._emit("notification")


def _match(brief: list[Card], card: Card) -> Card | None:
    """The card `card` replaces: the one with its id, else the one for its topic."""
    same_id = next((b for b in brief if b.id == card.id), None)
    if same_id is not None or not card.topic_id:
        return same_id
    return next((b for b in brief if b.topic_id == card.topic_id), None)
