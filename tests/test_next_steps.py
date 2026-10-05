from conftest import decide, until
from test_memory import doc_op, section_op, topic_op
from test_reasoning_loop import memory_answer

from quintessa.executors.generative_ui_executor import SCHEMA
from quintessa.models import Answer, InputEvent, InputKind, QuestionPurpose, SessionStatus


def section_with(id, doc_id, suggested, status="in progress"):
    op = section_op(id, doc_id)
    op["section"].update(suggested_actions=list(suggested), status=status)
    return op


def plan_dinner(script, *sections):
    script.on("decide", decide("memory", "save the plan"))
    script.on(
        "capability:memory",
        memory_answer(topic_op("topic-dinner", "Dinner"), doc_op("doc-dinner", "topic-dinner"), *sections),
    )


def next_step_questions(runtime):
    return [q for q in runtime.questions.pending.values() if q.purpose == QuestionPurpose.NEXT_STEP]


async def test_finished_session_offers_its_next_steps_in_the_sheet(script, make_runtime):
    plan_dinner(script, section_with("sec-place", "doc-dinner", ["Book Zuni for 7pm", "Text Jane the plan"]))
    runtime = make_runtime(script)

    session = await runtime.run(InputEvent(InputKind.TEXT, "plan dinner with Jane"))

    assert session.status == SessionStatus.COMPLETE  # nothing waits on the offer
    [question] = next_step_questions(runtime)
    assert question.prompt == "What next for Dinner?"
    assert question.fields[0].options == ["Book Zuni for 7pm", "Text Jane the plan"]
    assert (question.document_id, question.section_id, question.topic_id) == ("doc-dinner", "sec-place", "topic-dinner")
    assert question.user_waiting  # the user just asked, so the sheet opens by itself
    assert session.steps[-1].capability == "next_steps"
    assert "Book Zuni for 7pm" in session.steps[-1].summary

    # picking a step starts a session that does it
    script.on("decide", decide("memory", "book it"))
    script.on("capability:memory", memory_answer(summary="booked"))
    assert runtime.answer(Answer(question.id, {"step": "Book Zuni for 7pm"}))
    await until(lambda: len(runtime.store.sessions) == 2)
    await runtime.wait_idle()
    follow_up = next(s for s in runtime.store.sessions.values() if s.id != session.id)
    assert '"Book Zuni for 7pm"' in follow_up.trigger.content
    assert "section_id: sec-place" in follow_up.trigger.content
    assert follow_up.trigger.source == "user" and follow_up.status == SessionStatus.COMPLETE
    assert f"user picked 'Book Zuni for 7pm'; started {follow_up.id}" in session.steps[-1].summary
    assert not next_step_questions(runtime)


async def test_skipping_starts_nothing_and_the_same_steps_are_not_offered_again(script, make_runtime):
    plan_dinner(script, section_with("sec-place", "doc-dinner", ["Book Zuni"]))
    runtime = make_runtime(script)
    first = await runtime.run(InputEvent(InputKind.TEXT, "plan dinner"))
    [question] = next_step_questions(runtime)

    runtime.answer(Answer(question.id, dismissed=True))
    await until(lambda: "skipped" in first.steps[-1].summary)
    assert len(runtime.store.sessions) == 1

    plan_dinner(script, section_with("sec-place", "doc-dinner", ["Book Zuni"]))
    script.on("brief_refresh", {"cards": [], "questions": []})
    again = await runtime.run(InputEvent(InputKind.MESSAGE, "Jane: still on?", sender="Jane"))
    assert not next_step_questions(runtime)
    assert all(s.capability != "next_steps" for s in again.steps)


async def test_new_next_steps_replace_the_waiting_ones(script, make_runtime):
    plan_dinner(script, section_with("sec-place", "doc-dinner", ["Book Zuni"]))
    runtime = make_runtime(script)
    first = await runtime.run(InputEvent(InputKind.TEXT, "plan dinner"))
    [old] = next_step_questions(runtime)

    plan_dinner(script, section_with("sec-place", "doc-dinner", ["Book Nopa"]))
    script.on("brief_refresh", {"cards": [], "questions": []})
    await runtime.run(InputEvent(InputKind.MESSAGE, "Jane: Zuni is full", source="sms", sender="Jane"))

    [new] = next_step_questions(runtime)
    assert new.id != old.id and new.fields[0].options == ["Book Nopa"]
    assert not new.user_waiting  # an incoming message: the user is not looking
    await until(lambda: "withdrew" in first.steps[-1].summary)


async def test_finished_or_untouched_sections_offer_nothing(script, make_runtime):
    plan_dinner(script, section_with("sec-place", "doc-dinner", ["Book Zuni"], status="Done"))
    runtime = make_runtime(script)
    session = await runtime.run(InputEvent(InputKind.TEXT, "plan dinner"))
    assert not next_step_questions(runtime)
    assert all(s.capability != "next_steps" for s in session.steps)

    # a later session that changes nothing in the document offers nothing either
    script.on("decide", decide("memory"))
    script.on("capability:memory", memory_answer())
    await runtime.run(InputEvent(InputKind.TEXT, "thanks"))
    assert not next_step_questions(runtime)


async def test_steps_are_capped_and_span_sections(script, make_runtime):
    plan_dinner(
        script,
        section_with("sec-place", "doc-dinner", ["Book Zuni", "Call Nopa", "Book Zuni"]),
        section_with("sec-guests", "doc-dinner", ["Text Jane", "Text Sam", "Text Ali"]),
    )
    runtime = make_runtime(script)
    await runtime.run(InputEvent(InputKind.TEXT, "plan dinner"))
    [question] = next_step_questions(runtime)
    assert question.fields[0].options == ["Book Zuni", "Call Nopa", "Text Jane", "Text Sam"]
    assert question.section_id is None  # more than one section: the question is about the document


async def test_clear_drops_waiting_next_steps(script, make_runtime):
    plan_dinner(script, section_with("sec-place", "doc-dinner", ["Book Zuni"]))
    runtime = make_runtime(script)
    await runtime.run(InputEvent(InputKind.TEXT, "plan dinner"))
    assert next_step_questions(runtime)
    await runtime.clear()
    assert not runtime.questions.pending and not runtime.offered_steps


def test_the_model_cannot_ask_a_next_step_question():
    assert "next_step" not in SCHEMA["properties"]["purpose"]["enum"]


async def test_next_steps_open_at_once_after_the_user_answered_the_session(script, make_runtime):
    script.on("decide", decide("generative_ui", "which night"), decide("memory", "save the night"))
    script.on(
        "capability:generative_ui",
        {
            "prompt": "Which night?",
            "purpose": "disambiguation",
            "context": "",
            "fields": [{"name": "n", "kind": "option", "label": "", "options": ["Tue", "Wed"], "option_details": []}],
            "document_id": None,
            "section_id": None,
            "topic_id": None,
            "tool": None,
            "function": None,
        },
    )
    script.on(
        "capability:memory",
        memory_answer(
            topic_op("topic-dinner", "Dinner"),
            doc_op("doc-dinner", "topic-dinner"),
            section_with("sec-place", "doc-dinner", ["Book Zuni"]),
        ),
    )
    runtime = make_runtime(script)
    session = runtime.submit(InputEvent(InputKind.MESSAGE, "Jane: dinner this week?", source="sms", sender="Jane"))
    await until(lambda: session.status == SessionStatus.WAITING_FOR_USER)
    asked = runtime.questions.pending[session.pending_question_id]
    assert not asked.user_waiting  # Jane's text: the user was not looking

    runtime.answer(Answer(asked.id, {"n": "Wed"}))
    await runtime.wait_idle()
    [question] = next_step_questions(runtime)
    assert question.user_waiting  # they just answered, so they are still looking
