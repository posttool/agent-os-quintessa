from __future__ import annotations

import asyncio
from collections.abc import Callable

from quintessa.models import Answer, Question


class QuestionBroker:
    """Holds generated UI that reasoning loops are waiting on. A surface
    answers with a Answer; the waiting loop resumes with it."""

    def __init__(self) -> None:
        self.pending: dict[str, Question] = {}
        self._futures: dict[str, asyncio.Future[Answer]] = {}
        self._listeners: list[Callable[[Question], None]] = []

    def on_question(self, listener: Callable[[Question], None]) -> None:
        self._listeners.append(listener)

    async def ask(self, question: Question) -> Answer:
        future: asyncio.Future[Answer] = asyncio.get_running_loop().create_future()
        self.pending[question.id] = question
        self._futures[question.id] = future
        for listener in self._listeners:
            listener(question)
        try:
            return await future
        finally:
            self.pending.pop(question.id, None)
            self._futures.pop(question.id, None)

    def answer(self, answer: Answer) -> bool:
        future = self._futures.get(answer.question_id)
        if future is None or future.done():
            return False
        future.set_result(answer)
        return True

    def withdraw(self, question_id: str, reason: str) -> bool:
        """Take back a question that new information answered or made moot.
        The waiting loop resumes as if it were dismissed, told why."""
        return self.answer(Answer(question_id, dismissed=True, withdrawn=True, withdrawn_reason=reason))

    def cancel_all(self) -> None:
        for future in self._futures.values():
            if not future.done():
                future.cancel()
