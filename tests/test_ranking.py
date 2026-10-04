import json
from datetime import timedelta

import httpx
from conftest import decide

from quintessa.clock import now
from quintessa.decide import BriefRanker, SystemOneClient
from quintessa.device import BriefItem
from quintessa.device.salience import Salience, Suppression, proximity, suppression
from quintessa.models import InputEvent, InputKind, Topic
from quintessa.tools.builtin import _set_brief


def card(text, topic_id=None, urgency=None, relevance=0.5, affinity=0.5, due_in=None, label="normal"):
    due = now() + due_in if due_in is not None else None
    return BriefItem(text, topic_id, urgency=label, due_at=due, salience=Salience(urgency, relevance, affinity))


def texts(runtime):
    return [b.text for b in runtime.device.state.brief]


async def test_the_brief_is_ordered_by_salience(script, make_runtime):
    runtime = make_runtime(script)
    runtime.device.set_brief(
        [
            card("Screen time report", urgency=0.1, relevance=0.2, affinity=0.1),
            card("Rain in 12 minutes", urgency=0.5, relevance=0.9, affinity=0.1, due_in=timedelta(minutes=12)),
            card("Standup with video link", urgency=0.9, relevance=0.8, affinity=0.6, due_in=timedelta(minutes=15)),
            card("Plumber at 2pm", urgency=0.8, relevance=0.5, affinity=0.3, due_in=timedelta(hours=5)),
        ]
    )
    assert texts(runtime) == ["Standup with video link", "Rain in 12 minutes", "Plumber at 2pm", "Screen time report"]
    top = runtime.device.state.brief[0].salience
    assert 0.9 < top.proximity < 1 and top.score > 0.8


def test_proximity_halves_every_two_hours():
    at = now()
    assert proximity(None, at) == 0
    assert proximity(at - timedelta(minutes=5), at) == 1  # happening now
    assert abs(proximity(at + timedelta(hours=2), at) - 0.5) < 1e-9
    assert abs(proximity(at + timedelta(hours=4), at) - 0.25) < 1e-9


def test_suppression_fades_and_ignoring_grows():
    at = now()
    dismissed = [Suppression("topic:t", "dismissed", at)]
    assert suppression("topic:t", None, at, dismissed, at) == -0.6
    assert (
        abs(suppression("topic:t", None, at, [Suppression("topic:t", "dismissed", at - timedelta(hours=12))], at) + 0.3)
        < 1e-9
    )
    assert suppression("topic:other", None, at, dismissed, at) == 0
    # unopened for 2h is fine; then it loses up to 0.4 over the next 10h
    assert suppression("k", None, at - timedelta(hours=2), [], at) == 0
    assert abs(suppression("k", None, at - timedelta(hours=7), [], at) + 0.2) < 1e-9
    assert suppression("k", at - timedelta(minutes=5), at - timedelta(hours=7), [], at) == 0  # opened just now


async def test_dismissing_pushes_a_topic_down_when_the_agent_brings_it_back(script, make_runtime):
    runtime = make_runtime(script)
    runtime.store.upsert_topic(Topic("t-sale", "Shoe sale"))
    device = runtime.device
    device.set_brief([card("Shoe sale ends today", "t-sale", urgency=0.6), card("Water the plants", urgency=0.4)])
    assert texts(runtime)[0] == "Shoe sale ends today"

    device.dismiss_brief(device.state.brief[0].id)
    assert texts(runtime) == ["Water the plants"]

    await _set_brief(
        {
            "items": json.dumps(
                [
                    {"text": "Shoe sale: 10% more off", "topic_id": "t-sale", "salience": {"urgency": 0.6}},
                    {"text": "Water the plants", "salience": {"urgency": 0.4}},
                ]
            )
        },
        runtime,
    )
    sale = next(b for b in device.state.brief if b.topic_id == "t-sale")
    assert texts(runtime) == ["Water the plants", "Shoe sale: 10% more off"]
    assert sale.salience.suppression == -0.6


async def test_snoozed_cards_come_back_later_ranked_lower(script, make_runtime):
    runtime = make_runtime(script)
    device = runtime.device
    device.set_brief([card("Call the bank", urgency=0.7)])
    first = device.state.brief[0]
    device.snooze_brief(first.id, now() + timedelta(hours=1))
    assert device.state.brief == [] and device.state.snoozed == [first]

    device.prune_brief(now())
    assert device.state.brief == []  # not yet
    device.prune_brief(now() + timedelta(hours=1, minutes=1))
    assert [b.id for b in device.state.brief] == [first.id] and device.state.snoozed == []
    assert device.state.brief[0].snoozed_until is None and device.state.brief[0].salience.suppression < 0


async def test_opening_a_card_stops_the_ignore_penalty(script, make_runtime):
    runtime = make_runtime(script)
    device = runtime.device
    old = card("Renew passport", urgency=0.3)
    old.updated_at = now() - timedelta(hours=12)
    device.set_brief([old])
    assert device.state.brief[0].salience.suppression == -0.4
    device.open_brief(old.id)
    assert device.state.brief[0].salience.suppression == 0


async def test_cards_without_scores_rank_by_their_urgency_label(script, make_runtime):
    runtime = make_runtime(script)
    runtime.device.set_brief([card("FYI", label="low"), card("Gate changed", label="urgent")])
    assert texts(runtime) == ["Gate changed", "FYI"]


# --- Jev scoring ------------------------------------------------------------


class FakeJevScores:
    """Answers the three score questions per card from a text -> (urgency, relevance, affinity) level map."""

    def __init__(self, levels: dict[str, tuple[int, int, int]]):
        self.levels = levels
        self.requests: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        u, r, a = self.levels[body["state"]["card"]["text"]]
        answers = {
            name: {"type": "score", "score": level, "confidence": 0.8, "legend": {}, "probabilities": {}}
            for name, level in (("urgency", u), ("relevance", r), ("affinity", a))
        }
        return httpx.Response(200, json={"model": "jev-test", "answers": answers})


def ranker(fake) -> BriefRanker:
    return BriefRanker(SystemOneClient("test-key", base_url="https://jev.test", transport=httpx.MockTransport(fake)))


async def test_jev_scores_new_cards_and_the_brief_reorders(script, make_runtime):
    fake = FakeJevScores({"Mom's birthday dinner": (3, 2, 3), "Coupon expires": (2, 1, 0)})
    script.on("decide", decide("tool_use"))
    script.on(
        "capability:tool_use",
        {
            "tool": "device",
            "function": "update_brief",
            "rationale": "test",
            "document_id": None,
            "section_id": None,
            "topic_id": None,
            "track_progress": False,
            "progress_stages": [],
            "permission_prompt": "",
            "arguments": [
                {
                    "name": "put",
                    "value": json.dumps(
                        [
                            {"text": "Coupon expires", "salience": {"urgency": 0.9, "relevance": 0.9, "affinity": 0.9}},
                            {"text": "Mom's birthday dinner", "salience": {"urgency": 0.1}},
                        ]
                    ),
                }
            ],
        },
    )
    runtime = make_runtime(script, brief_ranker=ranker(fake))
    session = await runtime.run(InputEvent(InputKind.MESSAGE, "Mom: dinner at 7 for my birthday?", sender="Mom"))

    assert texts(runtime) == ["Mom's birthday dinner", "Coupon expires"]  # Jev's scores replaced the agent's
    mom = runtime.device.state.brief[0].salience
    assert (mom.urgency, mom.relevance, mom.affinity) == (0.75, 2 / 3, 1.0) and mom.scored_by == "jev-test"
    assert session.steps[-1].capability == "brief_rank"
    assert fake.requests[0]["questions"]["urgency"]["type"] == "score"
    assert fake.requests[0]["state"]["context"]["recent"][-1]["sender"] == "Mom"

    # nothing changed: the next session asks Jev nothing
    await runtime.run(InputEvent(InputKind.TEXT, "thanks"))
    assert len(fake.requests) == 2


async def test_a_location_change_rescores_every_card(script, make_runtime):
    fake = FakeJevScores({"Pick up dry cleaning": (2, 3, 1)})
    runtime = make_runtime(script, brief_ranker=ranker(fake))
    runtime.device.set_brief([card("Pick up dry cleaning", urgency=0.3)])
    await runtime.run(InputEvent(InputKind.TEXT, "hi"))
    await runtime.run(InputEvent(InputKind.LOCATION, "Near Elm St Cleaners", source="ambient:location"))
    assert len(fake.requests) == 2
    assert fake.requests[1]["state"]["context"]["last_location"] == "Near Elm St Cleaners"


async def test_jev_ranking_follows_the_preference_and_failures_keep_agent_scores(script, make_runtime):
    def broken(request):
        return httpx.Response(500, json={})

    runtime = make_runtime(script, brief_ranker=ranker(broken))
    runtime.device.set_brief([card("Pay rent", urgency=0.8)])
    session = await runtime.run(InputEvent(InputKind.TEXT, "hi"))
    assert runtime.device.state.brief[0].salience.urgency == 0.8
    assert "kept the agent's scores (HTTP 500" in session.steps[-1].summary

    runtime.set_preferences(jev_rank=False)
    assert runtime.brief_ranker is None
