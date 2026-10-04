from __future__ import annotations

from typing import TYPE_CHECKING

from quintessa.executors.common import call_capability
from quintessa.executors.step_context import StepContext
from quintessa.executors.step_outcome import StepOutcome
from quintessa.llm import schema as s
from quintessa.models import (
    Answer,
    FieldKind,
    Question,
    QuestionField,
    QuestionPurpose,
)
from quintessa.oversight import record_permission
from quintessa.serde import to_dict

if TYPE_CHECKING:
    from quintessa.memory.store import MemoryStore

SCHEMA = s.obj(
    {
        "prompt": s.string("The question, in a few words."),
        "context": s.string("One short sentence on why you are asking, shown under the question."),
        "purpose": s.enum_of(QuestionPurpose),
        "fields": s.array(
            s.obj(
                {
                    "name": s.string(),
                    "kind": s.enum_of(FieldKind),
                    "label": s.string(),
                    "options": s.array(s.string()),
                }
            )
        ),
        "document_id": s.nullable(s.string()),
        "section_id": s.nullable(s.string()),
        "topic_id": s.nullable(s.string("Topic this question is about, when there is one.")),
        "tool": s.nullable(s.string("Tool whose function this permission authorizes.")),
        "function": s.nullable(s.string()),
    }
)


def question_topic(store: MemoryStore, topic_id: str | None, document_id: str | None) -> str | None:
    """The topic a question belongs to: the one named if it exists, else the
    topic of its document."""
    if topic_id and topic_id in store.topics:
        return topic_id
    doc = store.documents.get(document_id) if document_id else None
    return doc.topic_id if doc is not None else None


def build_question(session_id: str, data: dict, store: MemoryStore) -> Question:
    return Question(
        session_id=session_id,
        purpose=QuestionPurpose(data["purpose"]),
        prompt=data["prompt"],
        fields=[QuestionField(f["name"], FieldKind(f["kind"]), f["label"], f["options"]) for f in data["fields"]],
        document_id=data["document_id"],
        section_id=data["section_id"],
        tool=data["tool"],
        function=data["function"],
        topic_id=question_topic(store, data.get("topic_id"), data["document_id"]),
        context=data.get("context") or "",
    )


class GenerativeUIExecutor:
    async def run(self, ctx: StepContext) -> StepOutcome:
        result = await call_capability(ctx, SCHEMA)
        question = build_question(ctx.session.id, result.data, ctx.runtime.store)

        async def on_answer(answer: Answer) -> StepOutcome:
            permission = record_permission(ctx.session, ctx.runtime.store, question, answer)
            given = "dismissed" if answer.dismissed else answer.values
            summary = f"Asked '{question.prompt}'; user answered {given}"
            if answer.withdrawn:
                summary = (
                    f"Asked '{question.prompt}', then withdrew it before the user answered ({answer.withdrawn_reason})"
                )
            if permission:
                summary += f"; {question.tool}.{question.function} {'granted' if permission.granted else 'declined'}"
            return StepOutcome(
                output={"question": to_dict(question), "answer": to_dict(answer)},
                summary=summary,
                model=result.model,
            )

        return StepOutcome(
            output={"question": to_dict(question)},
            summary=f"Asked '{question.prompt}'",
            model=result.model,
            question=question,
            on_answer=on_answer,
        )
