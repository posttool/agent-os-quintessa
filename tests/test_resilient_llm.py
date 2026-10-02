import pytest

from quintessa.llm import (
    FatalLLMError,
    InvalidOutputError,
    LLMUnavailableError,
    ModelRoute,
    RefusalError,
    ResilientLLM,
    RetryableLLMError,
    ScriptedLLM,
)
from quintessa.llm import schema as s

SCHEMA = s.obj({"answer": s.string()})


def sequence(*answers):
    items = list(answers)
    return ScriptedLLM(lambda *_: items.pop(0))


async def test_retries_transient_errors_with_backoff():
    delays = []

    async def sleep(d):
        delays.append(d)

    client = sequence(RetryableLLMError("429"), RetryableLLMError("503"), {"answer": "ok"})
    llm = ResilientLLM([ModelRoute(client, "m1")], retries=2, base_delay=1.0, sleep=sleep)
    result = await llm.generate_json(system="", prompt="{}", schema=SCHEMA)
    assert result.data == {"answer": "ok"}
    assert result.attempts == 3
    assert delays == [1.0, 2.0]


async def test_falls_back_to_older_model_on_refusal_and_fatal_errors():
    first = sequence(RefusalError("no"))
    second = sequence(FatalLLMError("404 model"))
    third = sequence({"answer": "from older"})
    llm = ResilientLLM([ModelRoute(first, "new"), ModelRoute(second, "mid"), ModelRoute(third, "old")], retries=2)
    result = await llm.generate_json(system="", prompt="{}", schema=SCHEMA)
    assert result.model == "old"
    assert len(first.calls) == len(second.calls) == 1


async def test_output_not_matching_schema_is_retried_then_falls_back():
    async def sleep(_):
        pass

    bad = sequence({"wrong": 1}, InvalidOutputError("not json"))
    good = sequence({"answer": "fine"})
    llm = ResilientLLM([ModelRoute(bad, "a"), ModelRoute(good, "b")], retries=1, sleep=sleep)
    result = await llm.generate_json(system="", prompt="{}", schema=SCHEMA)
    assert result.model == "b" and len(bad.calls) == 2


async def test_all_models_failing_raises_with_every_failure():
    llm = ResilientLLM([ModelRoute(sequence(FatalLLMError("x")), "a"), ModelRoute(sequence(RefusalError("y")), "b")])
    with pytest.raises(LLMUnavailableError) as err:
        await llm.generate_json(system="", prompt="{}", schema=SCHEMA)
    assert len(err.value.failures) == 2
