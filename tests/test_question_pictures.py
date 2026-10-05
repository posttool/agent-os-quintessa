"""Multi-select questions with quantities, tool pictures next to options, and
the chosen option's picture shown in the document."""

import json

import httpx
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
from quintessa.tools.picture_search import FoundPicture, WebPictures, find_real_pictures, pictures_in_json

MENU = {
    "status": "done",
    "result": "Margherita $14, Diavola $16, Coke $3",
    "progress_stages": [],
    "pictures": [
        {"caption": "Margherita", "kind": "photo", "emoji": "🍕", "image_url": None, "search_query": ""},
        {"caption": "Diavola", "kind": "photo", "emoji": "🌶️", "image_url": None, "search_query": ""},
        {"caption": "Coke", "kind": "logo", "emoji": "🥤", "image_url": None, "search_query": ""},
        {"caption": " ", "kind": "photo", "emoji": "", "image_url": None, "search_query": ""},
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
    assert "3 × Diavola, Coke" in next(s for s in session.steps if s.capability == "generative_ui").summary
    pictures = agent.store.documents["doc-dinner"].section("sec-order").pictures
    assert [p.caption for p in pictures] == ["Diavola"]


def test_good_pictures_are_photos_that_are_not_tiny():
    assert Picture("Pad thai").good
    assert not Picture("Logo", PictureKind.LOGO).good
    assert not Picture("Tiny", url="https://x.test/a.jpg", width=120, height=90).good
    assert Picture("Big", url="https://x.test/a.jpg", width=800, height=600).good


def commons_transport(seen):
    """Wikimedia Commons answering a file search, plus image hosts: real.jpg
    loads, broken.jpg is a page, not an image."""

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "commons.wikimedia.org":
            pages = {
                "1": {"index": 2, "imageinfo": [info("big.jpg", 1600, 1200)]},
                "2": {"index": 1, "imageinfo": [info("tiny.jpg", 100, 80)]},
                "3": {"index": 3, "imageinfo": [{**info("drawing.svg", 900, 900), "mime": "image/svg+xml"}]},
            }
            if "nothing" in request.url.params["gsrsearch"]:
                pages = {}
            return httpx.Response(200, json={"query": {"pages": pages}})
        if request.url.path.endswith("real.jpg"):
            return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"jpeg")
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html>")

    return httpx.MockTransport(handle)


def info(name, width, height):
    return {
        "mime": "image/jpeg",
        "width": width,
        "height": height,
        "url": f"https://upload.wikimedia.org/{name}",
        "thumburl": f"https://upload.wikimedia.org/800px-{name}",
        "thumbwidth": 800,
        "thumbheight": int(800 * height / width),
        "descriptionurl": f"https://commons.wikimedia.org/wiki/File:{name}",
    }


async def test_web_pictures_keep_app_images_that_load_and_search_for_the_rest():
    seen = []
    search = WebPictures(httpx.AsyncClient(transport=commons_transport(seen)))
    passed = Picture("Margherita", url="https://app.test/real.jpg")
    broken = Picture("Diavola", url="https://app.test/broken.jpg")
    plain = Picture("Funghi")
    missing = Picture("Nothing")
    await find_real_pictures(
        search,
        [(passed, "margherita pizza"), (broken, "diavola pizza"), (plain, "funghi pizza"), (missing, "nothing")],
    )

    assert passed.url == "https://app.test/real.jpg"  # passed through, no search
    # the first usable search result: big enough and a photo format
    assert broken.url == plain.url == "https://upload.wikimedia.org/800px-big.jpg"
    assert (plain.width, plain.height, plain.credit) == (800, 600, "Wikimedia Commons")
    assert plain.page_url.endswith("File:big.jpg")
    assert missing.url == "" and missing.good  # nothing found: drawn instead
    searches = [r for r in seen if r.url.host == "commons.wikimedia.org"]
    assert len(searches) == 3

    await find_real_pictures(search, [(Picture("Funghi"), "Funghi Pizza ")])
    assert len([r for r in seen if r.url.host == "commons.wikimedia.org"]) == 3  # cached


async def test_simulated_tools_get_real_pictures(script, make_runtime):
    class Found:
        async def find(self, query):
            return FoundPicture(f"https://img.test/{query.replace(' ', '-')}.jpg", 800, 600, "", "Test")

        async def loads(self, url):
            return False

    pictured = {**MENU, "pictures": [{**MENU["pictures"][0], "search_query": "margherita pizza"}]}
    script.on("decide", decide("tool_use"))
    script.on("capability:tool_use", call("pizzeria", "menu"))
    script.on("tool:pizzeria.menu", pictured)
    runtime = make_runtime(script, picture_search=Found())
    runtime.store.put_tool(menu_tool())
    session = runtime.submit(InputEvent(InputKind.TEXT, "menu"))
    await until(lambda: session.status == SessionStatus.COMPLETE)

    picture = runtime.store.tools["pizzeria"].history[-1].pictures[0]
    assert picture.url == "https://img.test/margherita-pizza.jpg" and picture.width == 800


def test_web_api_images_pass_through():
    body = {
        "results": [
            {"name": "Kin Khao", "photo": {"url": "https://cdn.test/kk.jpg", "width": 1200, "height": 800}},
            {"title": "Lers Ros", "thumbnail_url": "https://cdn.test/lr.jpg"},
            {"name": "No image", "rating": 4.5},
            {"brand": {"name": "Uber", "logo": "https://cdn.test/logo.png"}},
        ]
    }
    pictures = pictures_in_json(json.dumps(body), "places")
    assert [(p.caption, p.kind, p.width) for p in pictures] == [
        ("Kin Khao", PictureKind.PHOTO, 1200),
        ("Lers Ros", PictureKind.THUMBNAIL, 0),
        ("Uber", PictureKind.LOGO, 0),
    ]
    assert pictures_in_json("not json", "places") == []
