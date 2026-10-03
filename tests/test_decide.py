import json

import httpx

from quintessa.decide import NextStepDecider, SystemOneClient, shadow_decider_from_env
from quintessa.decide.report import agreement_report
from quintessa.models import InputEvent, InputKind, ReasoningSession, SessionStatus
from quintessa.serde import from_dict, to_dict

from conftest import decide
from test_reasoning_loop import memory_answer
from test_memory import topic_op


class FakeJev:
    """Answers /v1/systemone with a queued choice per call, recording requests."""

    def __init__(self, *choices: str, status: int = 200):
        self.choices = list(choices)
        self.status = status
        self.requests: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/systemone"
        assert request.headers["authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        self.requests.append(body)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "nope"})
        pick = self.choices.pop(0) if self.choices else "done"
        options = body["questions"]["next_step"]["criteria"]
        rest = (1 - 0.9) / (len(options) - 1)
        probabilities = {k: 0.9 if k == pick else rest for k in options}
        return httpx.Response(200, json={
            "model": "jev-test",
            "answers": {"next_step": {"type": "choice", "choice": pick, "probabilities": probabilities, "confidence": 0.8}},
            "usage": {"input_tokens": 100, "output_tokens": 1},
        })


def decider(fake: FakeJev) -> NextStepDecider:
    return NextStepDecider(SystemOneClient("test-key", base_url="https://jev.test", transport=httpx.MockTransport(fake)))


async def test_shadow_records_jev_beside_the_llm_without_steering(script, make_runtime):
    script.on("decide", decide("memory", "save the dinner idea"))
    script.on("capability:memory", memory_answer(topic_op("topic-dinner", "Dinner Plans")))
    fake = FakeJev("tool_use", "done")  # disagrees on the first step, agrees on done
    runtime = make_runtime(script, shadow=decider(fake))

    session = await runtime.run(InputEvent(InputKind.MESSAGE, "Jane: zuni on tuesday?", sender="Jane"))

    assert session.status == SessionStatus.COMPLETE
    assert [s.capability for s in session.steps] == ["memory"]  # the LLM still drives
    first, last = session.shadow_decisions
    assert (first.step_index, first.llm_choice, first.choice, first.agrees) == (0, "memory", "tool_use", False)
    assert (last.step_index, last.llm_choice, last.choice, last.agrees) == (1, "done", "done", True)
    assert first.model == "jev-test" and first.confidence == 0.8 and first.probabilities["tool_use"] == 0.9

    # the question is a choice over every capability plus done, criteria from the capability files
    question = fake.requests[0]["questions"]["next_step"]
    assert question["type"] == "choice"
    assert set(question["criteria"]) == {*runtime.capabilities, "done"}
    assert question["criteria"]["memory"] == runtime.capabilities["memory"].choose_when != ""
    assert fake.requests[0]["model"] == "jev-latest"
    # the same context the LLM controller saw, without the capability list the criteria carry
    first_llm, second_llm = script.prompts["decide"]
    for request, llm_prompt in zip(fake.requests, (first_llm, second_llm)):
        assert {k: v for k, v in llm_prompt.items() if k not in ("capabilities", "now")} == {
            k: v for k, v in request["state"].items() if k != "now"
        }
    assert "capabilities" not in fake.requests[0]["state"]
    second = fake.requests[1]["state"]
    assert second["steps_so_far"][0]["capability"] == "memory"
    assert second["memory"]["topics"][0]["title"] == "Dinner Plans"


async def test_a_failing_endpoint_never_fails_the_session(script, make_runtime):
    script.on("decide", decide("memory"))
    script.on("capability:memory", memory_answer())
    runtime = make_runtime(script, shadow=decider(FakeJev(status=403)))

    session = await runtime.run(InputEvent(InputKind.TEXT, "hello"))

    assert session.status == SessionStatus.COMPLETE
    assert [d.error.startswith("HTTP 403") for d in session.shadow_decisions] == [True, True]


async def test_no_shadow_by_default(script, make_runtime):
    runtime = make_runtime(script)
    session = await runtime.run(InputEvent(InputKind.TEXT, "hello"))
    assert session.shadow_decisions == []


def test_shadow_decisions_survive_a_round_trip():
    session = ReasoningSession(trigger=InputEvent(InputKind.TEXT, "hi"))
    data = to_dict(session)
    data.pop("shadow_decisions")  # state saved before shadow mode existed still loads
    assert from_dict(ReasoningSession, data).shadow_decisions == []


def test_env_turns_shadow_on_with_a_key(monkeypatch):
    for name in ("QUINTESSA_JEV_API_KEY", "TYPESAFE_API_KEY", "QUINTESSA_DECIDER", "QUINTESSA_JEV_URL"):
        monkeypatch.delenv(name, raising=False)
    assert shadow_decider_from_env() is None
    monkeypatch.setenv("QUINTESSA_JEV_API_KEY", "k")
    monkeypatch.setenv("QUINTESSA_JEV_URL", "https://gev.example.run.app/")
    shadow = shadow_decider_from_env()
    assert shadow is not None and shadow.client.base_url == "https://gev.example.run.app"
    assert shadow.client.label == "jev-latest@gev.example.run.app"
    monkeypatch.setenv("QUINTESSA_DECIDER", "llm")
    assert shadow_decider_from_env() is None


async def test_agreement_report(script, make_runtime):
    script.on("decide", decide("memory"), decide("tool_use"))
    script.on("capability:memory", memory_answer())
    script.on("capability:tool_use", {
        "tool": "device", "function": "set_island", "arguments": [], "rationale": "", "document_id": None,
        "section_id": None, "track_progress": False, "progress_stages": [], "permission_prompt": "",
    })
    runtime = make_runtime(script, shadow=decider(FakeJev("memory", "memory", "done")))
    session = await runtime.run(InputEvent(InputKind.TEXT, "hello"))

    report = agreement_report([session])

    assert "3 decisions in shadow, 3 answered, 0 failed" in report
    assert "agreement with the LLM: 2/3 (67%)" in report
    assert "tool_use        0/1 (0%)         memory x1" in report


# --- ambient filter ------------------------------------------------------------------

from quintessa.decide import AmbientFilter, ambient_filter_from_env


def jev_noul(p: float, requests: list | None = None, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if requests is not None:
            requests.append(body)
        if status != 200:
            return httpx.Response(status, json={})
        return httpx.Response(200, json={"model": "jev-test", "answers": {"matters": {"type": "noul", "noul": p}}})
    return AmbientFilter(SystemOneClient("test-key", base_url="https://jev.test", transport=httpx.MockTransport(handler)))


async def test_filter_skips_ambient_noise_without_any_llm_call(script, make_runtime):
    requests = []
    runtime = make_runtime(script, ambient_filter=jev_noul(0.1, requests))
    session = await runtime.run(InputEvent(InputKind.MESSAGE, "20% off fall bowls", source="ambient:email", sender="Sweetgreen"))

    assert session.status == SessionStatus.COMPLETE and session.steps == []
    assert session.prefilter.skipped and session.prefilter.matters == 0.1 and session.prefilter.threshold == 0.3
    assert "decide" not in script.prompts  # the LLM was never asked
    state = requests[0]["state"]
    assert state["event"] == {"kind": "message", "sender": "Sweetgreen", "content": "20% off fall bowls"}
    assert {"tracking", "documents", "people"} <= set(state)
    assert requests[0]["questions"]["matters"]["type"] == "noul"


async def test_filter_keeps_events_that_matter(script, make_runtime):
    script.on("decide", decide("memory"))
    script.on("capability:memory", memory_answer())
    runtime = make_runtime(script, ambient_filter=jev_noul(0.9))
    session = await runtime.run(InputEvent(InputKind.MESSAGE, "Mom: flight delayed to 4:40", source="ambient:sms"))
    assert not session.prefilter.skipped
    assert [s.capability for s in session.steps] == ["memory"]


async def test_filter_fails_open(script, make_runtime):
    runtime = make_runtime(script, ambient_filter=jev_noul(0.0, status=500))
    session = await runtime.run(InputEvent(InputKind.LOCATION, "Arrived at SFO", source="persona"))
    assert session.prefilter.error.startswith("HTTP 500") and not session.prefilter.skipped
    assert len(script.prompts["decide"]) == 1  # ran as usual


async def test_filter_never_touches_what_the_user_says(script, make_runtime):
    requests = []
    runtime = make_runtime(script, ambient_filter=jev_noul(0.0, requests))
    for source in ("user", "process:food_delivery", "persona:profile"):
        session = await runtime.run(InputEvent(InputKind.TEXT, "hi", source=source))
        assert session.prefilter is None
    assert requests == []


def test_filter_env_is_off_by_default(monkeypatch):
    for name in ("QUINTESSA_AMBIENT_FILTER", "QUINTESSA_AMBIENT_THRESHOLD", "QUINTESSA_JEV_API_KEY", "TYPESAFE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("QUINTESSA_JEV_API_KEY", "k")
    assert ambient_filter_from_env() is None
    monkeypatch.setenv("QUINTESSA_AMBIENT_FILTER", "1")
    monkeypatch.setenv("QUINTESSA_AMBIENT_THRESHOLD", "0.5")
    assert ambient_filter_from_env().threshold == 0.5


async def test_jev_preference_switches_both_deciders_off_and_on(script, make_runtime):
    script.on("decide", decide("memory"))
    script.on("capability:memory", memory_answer())
    fake, requests = FakeJev(), []
    runtime = make_runtime(script, shadow=decider(fake), ambient_filter=jev_noul(0.0, requests))

    runtime.set_preferences(jev=False)
    session = await runtime.run(InputEvent(InputKind.MESSAGE, "20% off", source="ambient:email"))
    assert session.prefilter is None and session.shadow_decisions == [] and [s.capability for s in session.steps] == ["memory"]
    assert fake.requests == [] and requests == []

    runtime.set_preferences(jev=True, jev_shadow=False)
    session = await runtime.run(InputEvent(InputKind.MESSAGE, "20% off", source="ambient:email"))
    assert session.prefilter.skipped and fake.requests == []
    assert runtime.jev_status() == {"available": True, "model": "jev-latest@jev.test", "threshold": 0.3,
                                    "jev": True, "jev_shadow": False, "jev_filter": True, "jev_drive": False}


def test_jev_options_from_env(monkeypatch):
    from quintessa.decide import jev_options_from_env

    for name in ("QUINTESSA_AMBIENT_FILTER", "QUINTESSA_DECIDER", "QUINTESSA_JEV_API_KEY", "TYPESAFE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert jev_options_from_env() == {}
    monkeypatch.setenv("QUINTESSA_JEV_API_KEY", "k")
    options = jev_options_from_env()
    assert options["shadow"] and options["ambient_filter"]  # both exist so users can switch them on
    assert (options["jev_shadow_default"], options["jev_filter_default"]) == (True, False)
    monkeypatch.setenv("QUINTESSA_DECIDER", "llm")
    monkeypatch.setenv("QUINTESSA_AMBIENT_FILTER", "1")
    options = jev_options_from_env()
    assert (options["jev_shadow_default"], options["jev_filter_default"]) == (False, True)


async def test_jev_can_drive_the_next_step(script, make_runtime):
    script.on("capability:memory", memory_answer(topic_op("topic-dinner", "Dinner Plans")))
    fake = FakeJev("memory", "done")
    runtime = make_runtime(script, shadow=decider(fake))
    runtime.set_preferences(jev_drive=True)

    session = await runtime.run(InputEvent(InputKind.MESSAGE, "Jane: zuni on tuesday?", sender="Jane"))

    assert "decide" not in script.prompts  # the LLM never picked a step
    assert [(s.capability, s.decided_by, s.rationale) for s in session.steps] == [("memory", "jev", "Jev p 0.90")]
    assert [(d.choice, d.drove, d.llm_choice) for d in session.shadow_decisions] == [("memory", True, ""), ("done", True, "")]
    assert "No shadow decisions" in agreement_report([session])  # driven choices are not agreement data


async def test_the_llm_takes_over_when_jev_fails_to_drive(script, make_runtime):
    script.on("decide", decide("memory"))
    script.on("capability:memory", memory_answer())
    runtime = make_runtime(script, shadow=decider(FakeJev(status=500)))
    runtime.set_preferences(jev_drive=True)

    session = await runtime.run(InputEvent(InputKind.TEXT, "hello"))

    assert [(s.capability, s.decided_by) for s in session.steps] == [("memory", "")]
    assert len(script.prompts["decide"]) == 2
    assert [(d.drove, d.llm_choice, d.error[:8]) for d in session.shadow_decisions] == [(False, "memory", "HTTP 500"), (False, "done", "HTTP 500")]
