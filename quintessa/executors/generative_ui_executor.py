from __future__ import annotations

from typing import TYPE_CHECKING

from quintessa.executors.common import call_capability
from quintessa.executors.step_context import StepContext
from quintessa.executors.step_outcome import StepOutcome
from quintessa.llm import schema as s
from quintessa.models import (
    Answer,
    FieldKind,
    Picture,
    Question,
    QuestionField,
    QuestionOption,
    QuestionPurpose,
)
from quintessa.oversight import record_permission
from quintessa.serde import to_dict
from quintessa.tools.runner import recent_pictures

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
                    "option_details": s.array(
                        s.obj(
                            {
                                "option": s.string("One of this field's options, exactly."),
                                "picture_id": s.nullable(s.string("Id of a picture a tool returned for it.")),
                                "takes_quantity": s.boolean("The user says how many when they pick it."),
                            }
                        ),
                        "Only for options that have a picture or take a quantity.",
                    ),
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


CHOICE_KINDS = (FieldKind.OPTION, FieldKind.SUGGESTION, FieldKind.MULTI_OPTION)
SHOWN_PICTURES = 4  # chosen pictures a document or section keeps


def build_question(session_id: str, data: dict, store: MemoryStore, pictures: dict[str, Picture]) -> Question:
    return Question(
        session_id=session_id,
        purpose=QuestionPurpose(data["purpose"]),
        prompt=data["prompt"],
        fields=[build_field(f, pictures) for f in data["fields"]],
        document_id=data["document_id"],
        section_id=data["section_id"],
        tool=data["tool"],
        function=data["function"],
        topic_id=question_topic(store, data.get("topic_id"), data["document_id"]),
        context=data.get("context") or "",
    )


def build_field(data: dict, pictures: dict[str, Picture]) -> QuestionField:
    """A field with its options' pictures and quantities. Unknown picture ids
    are dropped, and an option the model gave no picture gets the picture a
    tool returned with exactly its name, so a menu's dishes keep their photos."""
    field = QuestionField(data["name"], FieldKind(data["kind"]), data["label"], data["options"])
    if field.kind not in CHOICE_KINDS:
        return field
    by_caption = {p.caption.strip().lower(): p for p in pictures.values()}
    given = {d["option"]: d for d in data.get("option_details", []) if d["option"] in field.options}
    for option in field.options:
        detail = given.get(option, {})
        picture = pictures.get(detail.get("picture_id") or "") or by_caption.get(option.strip().lower())
        quantity = bool(detail.get("takes_quantity")) and field.kind == FieldKind.MULTI_OPTION
        if picture or quantity:
            field.option_details.append(QuestionOption(option, picture, quantity))
    return field


def chosen_options(question: Question, answer: Answer) -> list[tuple[QuestionField, str]]:
    """Every option the user picked, field by field."""
    picked = []
    for f in question.fields:
        if f.kind == FieldKind.MULTI_OPTION:
            picked += [(f, sel.option) for sel in answer.selections.get(f.name, [])]
        elif f.kind in CHOICE_KINDS and answer.values.get(f.name) in f.options:
            picked.append((f, answer.values[f.name]))
    return picked


def show_chosen_pictures(store: MemoryStore, question: Question, answer: Answer) -> list[Picture]:
    """Put the good pictures of what the user chose into the document the
    question belongs to: its section when it names one, else the document
    (its own, or its topic's). Returns the pictures placed."""
    if answer.dismissed:
        return []
    chosen = []
    for f, option in chosen_options(question, answer):
        detail = f.detail(option)
        if detail and detail.picture and detail.picture.good:
            chosen.append(detail.picture)
    if not chosen:
        return []
    document_id = question.document_id
    if not document_id and question.topic_id in store.topics:
        document_id = store.topics[question.topic_id].document_id
    doc = store.documents.get(document_id or "")
    if doc is None:
        return []
    target = (doc.section(question.section_id) if question.section_id else None) or doc
    ids = {p.id for p in chosen}
    target.pictures = [*[p for p in target.pictures if p.id not in ids], *chosen][-SHOWN_PICTURES:]
    store.upsert_document(doc)
    return chosen


def answer_summary(question: Question, answer: Answer) -> str:
    if answer.withdrawn:
        return f"Asked '{question.prompt}', then withdrew it before the user answered ({answer.withdrawn_reason})"
    return f"Asked '{question.prompt}'; user answered {'dismissed' if answer.dismissed else answer.values}"


class GenerativeUIExecutor:
    async def run(self, ctx: StepContext) -> StepOutcome:
        result = await call_capability(ctx, SCHEMA)
        store = ctx.runtime.store
        question = build_question(ctx.session.id, result.data, store, recent_pictures(ctx.runtime))

        async def on_answer(answer: Answer) -> StepOutcome:
            permission = record_permission(ctx.session, store, question, answer)
            summary = answer_summary(question, answer)
            if permission:
                summary += f"; {question.tool}.{question.function} {'granted' if permission.granted else 'declined'}"
            shown = show_chosen_pictures(store, question, answer)
            if shown:
                summary += f"; showing {', '.join(repr(p.caption) for p in shown)} in the document"
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
