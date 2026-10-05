"""Multi-select questions with quantities, tool pictures next to options, and
the chosen option's picture shown in the document."""

from conftest import decide, until
from test_api import api  # noqa: F401  (fixture)
from test_memory import doc_op, section_op, topic_op
from test_tools import call

from quintessa.models import (
    Answer,
    FieldKind,
    InputEvent,
    InputKind,
    OversightLevel,
    Picture,
    PictureKind,
    Selection,
    SessionStatus,
    Tool,
    ToolFunction,
    ToolKind,
)

MENU = {
    "status": "done",
    "result": "Margherita $14, Diavola $16, Coke $3",
    "progress_stages": [],
    "pictures": [
        {"caption": "Margherita", "kind": "photo", "emoji": "🍕"},
        {"caption": "Diavola", "kind": "photo", "emoji": "🌶️"},
        {"caption": "Coke", "kind": "logo", "emoji": "🥤"},
        {"caption": " ", "kind": "photo", "emoji": ""},
    ],
}


def menu_tool():
    return Tool(
        "pizzeria",
        "Pizza place",
        ToolKind.LLM,
        [ToolFunction("menu", "Show the menu", oversight=OversightLevel.AUTO)],
        grounding="You are a pizzeria.",
    )


def order_question(margherita_id):
    return {
        "prompt": "What should I order?",
        "purpose": "disambiguation",
        "context": "So I can place the order before 7",
        "fields": [
            {
                "name": "items",
                "kind": "multi_option",
                "label": "Pizzas and drinks",
                "options": ["Margherita", "Diavola", "Coke"],
                "option_details": [
                    {"option": "Margherita", "picture_id": margherita_id, "takes_quantity": True},
                    {"option": "Coke", "picture_id": "pic_made_up", "takes_quantity": True},
                    {"option": "Not an option", "picture_id": None, "takes_quantity": True},
                ],
            }
        ],
        "document_id": "doc-dinner",
        "section_id": "sec-order",
        "topic_id": "topic-dinner",
        "tool": None,
        "function": None,
    }


def scripted_order(script):
    script.on("decide", decide("memory"), decide("tool_use", "menu"), decide("generative_ui", "what to order"))
    script.on(
        "capability:memory",
        {
            "summary": "doc",
            "operations": [
                topic_op("topic-dinner", "Dinner"),
                doc_op("doc-dinner", "topic-dinner"),
                section_op("sec-order", "doc-dinner"),
            ],
        },
    )
    script.on("capability:tool_use", call("pizzeria", "menu"))
    script.on("tool:pizzeria.menu", MENU)

    def ask(payload):
        summary = payload["steps_so_far"][-1]["summary"]
        margherita = next(part.split(" ")[0] for part in summary.split("Pictures: ")[1].split("; "))
        return order_question(margherita)

    script.on("capability:generative_ui", ask)


async def test_multi_select_with_pictures_and_quantities(script, make_runtime):
    scripted_order(script)
    runtime = make_runtime(script)
    runtime.store.put_tool(menu_tool())
    asked = []
    runtime.questions.on_question(asked.append)

    session = runtime.submit(InputEvent(InputKind.TEXT, "order pizza"))
    await until(lambda: session.status == SessionStatus.WAITING_FOR_USER)

    # the tool step lists its pictures for the agent; blank captions are dropped
    assert session.steps[1].summary.count("pic_") == 3
    field = asked[0].fields[0]
    assert field.kind == FieldKind.MULTI_OPTION
    details = {d.option: d for d in field.option_details}
    assert details["Margherita"].picture.caption == "Margherita" and details["Margherita"].takes_quantity
    # an unknown id falls back to the picture with the option's name
    assert details["Coke"].picture.kind == PictureKind.LOGO
    # no id given: matched by name, no quantity
    assert details["Diavola"].picture.emoji == "🌶️" and not details["Diavola"].takes_quantity
    assert "Not an option" not in details

    runtime.answer(
        Answer(
            asked[0].id,
            {"items": "2 × Margherita, Coke"},
            {"items": [Selection("Margherita", 2), Selection("Coke")]},
        )
    )
    await until(lambda: session.status == SessionStatus.COMPLETE)

    # the Margherita photo goes in the section; the Coke logo does not
    section = runtime.store.documents["doc-dinner"].section("sec-order")
    assert [p.caption for p in section.pictures] == ["Margherita"]
    assert "showing 'Margherita' in the document" in session.steps[2].summary
    assert "2 × Margherita, Coke" in session.steps[2].summary


async def test_answer_api_turns_selections_into_text(api, script):  # noqa: F811
    scripted_order(script)
    agent = await api.host.agent("maya")
    agent.store.put_tool(menu_tool())
    await api.post("/api/input?user=maya", json={"content": "order pizza"})
    await until(lambda: bool(agent.questions.pending))
    question = next(iter(agent.questions.pending.values()))

    body = {"selections": {"items": [{"option": "Diavola", "quantity": 3}, {"option": "Coke", "quantity": 1}]}}
    assert (
        await api.post(
            f"/api/questions/{question.id}?user=maya", json={"selections": {"items": [{"option": "x", "quantity": 0}]}}
        )
    ).status_code == 422
    assert (await api.post(f"/api/questions/{question.id}?user=maya", json=body)).status_code == 200
    await agent.wait_idle()
    session = next(iter(agent.store.sessions.values()))
    assert "3 × Diavola, Coke" in session.steps[-1].summary
    pictures = agent.store.documents["doc-dinner"].section("sec-order").pictures
    assert [p.caption for p in pictures] == ["Diavola"]


def test_good_pictures_are_photos_that_are_not_tiny():
    assert Picture("Pad thai").good
    assert not Picture("Logo", PictureKind.LOGO).good
    assert not Picture("Tiny", url="https://x.test/a.jpg", width=120, height=90).good
    assert Picture("Big", url="https://x.test/a.jpg", width=800, height=600).good
