"""When a session finishes with next steps on the table, offer them in the
question sheet. A section the session changed that is still open and lists
suggested actions has next steps; each document gets one next-step question
with those actions as its options. Nothing waits on it: the session is
complete, and picking a step starts a new session that does it."""

from __future__ import annotations

from typing import TYPE_CHECKING

from quintessa.clock import now
from quintessa.device.focus import COMPLETE_STATUSES
from quintessa.models import (
    Answer,
    Document,
    DocumentSection,
    FieldKind,
    InputEvent,
    InputKind,
    Question,
    QuestionField,
    QuestionPurpose,
    ReasoningSession,
    TraceStep,
)
from quintessa.prompts import prompt
from quintessa.serde import to_dict

if TYPE_CHECKING:
    from quintessa.loop.runtime import AgentRuntime

PURPOSE = "next_steps"
FIELD = "step"
MAX_OPTIONS = 4


def open_next_steps(doc: Document, since) -> list[DocumentSection]:
    """Sections changed since `since` that are still open and suggest actions."""
    return [
        s
        for s in doc.sections
        if s.updated_at >= since and s.suggested_actions and s.status.strip().lower() not in COMPLETE_STATUSES
    ]


def next_step_options(sections: list[DocumentSection]) -> dict[str, str]:
    """The actions to offer, each with the section it came from, first come first."""
    options: dict[str, str] = {}
    for section in sections:
        for action in section.suggested_actions:
            if action.strip() and action not in options and len(options) < MAX_OPTIONS:
                options[action] = section.id
    return options


def offer_next_steps(runtime: AgentRuntime, session: ReasoningSession) -> TraceStep | None:
    """Ask a next-step question for each document this session left with
    next steps. A set of steps already offered for a document is not offered
    again; a different set replaces the question still waiting. Returns the
    trace step, or None when there was nothing to offer."""
    lines = []
    for doc in list(runtime.store.documents.values()):
        if doc.archived:
            continue
        sections = open_next_steps(doc, session.started_at)
        options = next_step_options(sections)
        if not options or runtime.offered_steps.get(doc.id) == tuple(options):
            continue
        for waiting in list(runtime.questions.pending.values()):
            if waiting.purpose == QuestionPurpose.NEXT_STEP and waiting.document_id == doc.id:
                runtime.questions.withdraw(waiting.id, "newer next steps")
        runtime.offered_steps[doc.id] = tuple(options)
        question = Question(
            session_id=session.id,
            purpose=QuestionPurpose.NEXT_STEP,
            prompt=f"What next for {doc.title}?",
            fields=[QuestionField(FIELD, FieldKind.OPTION, "Next step", list(options))],
            document_id=doc.id,
            section_id=next(iter(options.values())) if len({*options.values()}) == 1 else None,
            topic_id=doc.topic_id,
            context="Done for now. Pick a next step and I'll get on it.",
        )
        runtime.follow_up(_wait_for_pick(runtime, session, question, options))
        lines.append(f"{doc.title}: {', '.join(options)}")
    if not lines:
        return None
    step = TraceStep(len(session.steps), PURPOSE, "Offer the next steps", "the session left suggested actions open")
    step.summary = "offered " + "; ".join(lines)
    step.ended_at = now()
    session.steps.append(step)
    return step


async def _wait_for_pick(
    runtime: AgentRuntime, session: ReasoningSession, question: Question, options: dict[str, str]
) -> None:
    answer = await runtime.questions.ask(question)
    picked = (answer.values.get(FIELD) or "").strip()
    started = None
    if picked and not answer.dismissed:
        started = runtime.submit(InputEvent(InputKind.TEXT, _input(runtime, question, options, picked), device="phone"))
    _record(runtime, session, question, answer, picked, started)


def _input(runtime: AgentRuntime, question: Question, options: dict[str, str], picked: str) -> str:
    doc = runtime.store.documents.get(question.document_id or "")
    section = doc.section(options.get(picked) or question.section_id or "") if doc else None
    where = f" for {doc.title}" if doc else ""
    if section is not None:
        where += f', section "{section.title}" (document_id: {doc.id}, section_id: {section.id})'
    elif doc is not None:
        where += f" (document_id: {doc.id})"
    return prompt("next_step", step=picked, where=where)


def _record(
    runtime: AgentRuntime,
    session: ReasoningSession,
    question: Question,
    answer: Answer,
    picked: str,
    started: ReasoningSession | None,
) -> None:
    """Note on the finished session's trace what became of its next steps."""
    if answer.withdrawn:
        outcome = f"withdrew '{question.prompt}' ({answer.withdrawn_reason})"
    elif started is not None:
        outcome = f"user picked '{picked}'; started {started.id}"
    else:
        outcome = f"user skipped '{question.prompt}'"
    step = next((s for s in reversed(session.steps) if s.capability == PURPOSE), None)
    if step is None:
        return
    step.summary += f"; {outcome}"
    step.output.setdefault("answers", []).append({"question": to_dict(question), "answer": to_dict(answer)})
    runtime.store.put_session(session)
