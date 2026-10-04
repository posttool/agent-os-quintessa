from __future__ import annotations

import asyncio
from collections.abc import Callable

from quintessa.models import Answer, Question
from quintessa.models.answer import WITHDRAWN


class QuestionBroker:
    """Holds generated UI that reasoning loops are waiting on. A surface
    answers with a Answer; the waiting loop resumes with it."""

    def __init__(self) -> None:
        self.pending: dict[str, Question] = {}
        self._futures: dict[str, asyncio.Future[Answer]] = {}
        self._listeners: list[Callable[[Question], None]] = []

    def on_request(self, listener: Callable[[Question], None]) -> None:
        self._listeners.append(listener)

    async def ask(self, request: Question) -> Answer:
        future: asyncio.Future[Answer] = asyncio.get_running_loop().create_future()
        self.pending[request.id] = request
        self._futures[request.id] = future
        for listener in self._listeners:
            listener(request)
        try:
            return await future
        finally:
            self.pending.pop(request.id, None)
            self._futures.pop(request.id, None)

    def answer(self, response: Answer) -> bool:
        future = self._futures.get(response.question_id)
        if future is None or future.done():
            return False
        future.set_result(response)
        return True

    def withdraw(self, question_id: str, reason: str) -> bool:
        """Take back a question that new information answered or made moot.
        The waiting loop resumes as if it were dismissed, told why."""
        return self.answer(Answer(question_id, dismissed=True, surface_context=f"{WITHDRAWN}{reason}"))

    def cancel_all(self) -> None:
        for future in self._futures.values():
            if not future.done():
                future.cancel()
