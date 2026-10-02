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
    # the trimmed state: the trigger, then the chain so far and memory's outline
    assert fake.requests[0]["state"]["trigger"]["content"] == "Jane: zuni on tuesday?"
    assert fake.requests[0]["state"]["steps_so_far"] == []
    second = fake.requests[1]["state"]
    assert second["steps_so_far"][0]["capability"] == "memory"
    assert second["topics"][0]["title"] == "Dinner Plans"


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
