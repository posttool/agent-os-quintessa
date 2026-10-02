from types import SimpleNamespace

import anthropic
import httpx
import pytest
from google.genai import errors as genai_errors

from quintessa.llm import FatalLLMError, InvalidOutputError, RefusalError, RetryableLLMError
from quintessa.llm.claude import SERVER_FALLBACK_BETA, ClaudeAdapter
from quintessa.llm.gemini_vertex import GeminiVertexAdapter

SCHEMA = {"type": "object", "properties": {"a": {"type": "number"}}, "required": ["a"], "additionalProperties": False}


class FakeMessages:
    def __init__(self, result):
        self.result = result
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def claude_client(result):
    return SimpleNamespace(messages=FakeMessages(result), beta=SimpleNamespace(messages=FakeMessages(result)))


def claude_message(text='{"a": 1}', stop_reason="end_turn"):
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)])


async def call(adapter, model):
    return await adapter.generate_json(model=model, system="sys", prompt="p", schema=SCHEMA, max_tokens=100)


async def test_claude_structured_output_with_server_fallback():
    client = claude_client(claude_message())
    assert await call(ClaudeAdapter(client), "claude-opus-5-5") == {"a": 1}
    kwargs = client.beta.messages.kwargs
    assert kwargs["betas"] == [SERVER_FALLBACK_BETA] and kwargs["fallbacks"] == "default"
    assert kwargs["output_config"]["format"] == {"type": "json_schema", "schema": SCHEMA}
    assert kwargs["output_config"]["effort"] == "medium"


async def test_claude_on_vertex_uses_plain_messages():
    client = claude_client(claude_message())
    adapter = ClaudeAdapter(client, vertex_project="my-project")
    await call(adapter, "claude-opus-5-5")
    assert client.beta.messages.kwargs is None and client.messages.kwargs["model"] == "claude-opus-5-5"


async def test_claude_older_model_skips_server_fallback():
    client = claude_client(claude_message())
    await call(ClaudeAdapter(client), "claude-opus-4-8")
    assert client.messages.kwargs is not None and "fallbacks" not in client.messages.kwargs


@pytest.mark.parametrize(
    "message, error",
    [
        (claude_message(stop_reason="refusal"), RefusalError),
        (claude_message(stop_reason="max_tokens"), InvalidOutputError),
        (claude_message(text="not json"), InvalidOutputError),
    ],
)
async def test_claude_bad_responses(message, error):
    with pytest.raises(error):
        await call(ClaudeAdapter(claude_client(message)), "claude-opus-4-8")


def _status_error(cls, status):
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    return cls(message="err", response=response, body=None)


@pytest.mark.parametrize(
    "exc, error",
    [
        (_status_error(anthropic.RateLimitError, 429), RetryableLLMError),
        (_status_error(anthropic.InternalServerError, 500), RetryableLLMError),
        (_status_error(anthropic.BadRequestError, 400), FatalLLMError),
        (_status_error(anthropic.NotFoundError, 404), FatalLLMError),
    ],
)
async def test_claude_error_mapping(exc, error):
    with pytest.raises(error):
        await call(ClaudeAdapter(claude_client(exc)), "claude-opus-4-8")


class FakeModels:
    def __init__(self, result):
        self.result = result
        self.kwargs = None

    async def generate_content(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def gemini_client(result):
    models = FakeModels(result)
    return SimpleNamespace(aio=SimpleNamespace(models=models)), models


def gemini_response(text='{"a": 2}', reason="STOP"):
    return SimpleNamespace(candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=reason))], text=text)


async def test_gemini_structured_output():
    client, models = gemini_client(gemini_response())
    assert await call(GeminiVertexAdapter(client), "gemini-3.8-flash") == {"a": 2}
    config = models.kwargs["config"]
    assert models.kwargs["model"] == "gemini-3.8-flash"
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == SCHEMA
    assert config.system_instruction == "sys"


@pytest.mark.parametrize(
    "result, error",
    [
        (gemini_response(reason="SAFETY"), RefusalError),
        (gemini_response(reason="MAX_TOKENS"), InvalidOutputError),
        (gemini_response(text="nope"), InvalidOutputError),
        (genai_errors.APIError(429, {"error": {"message": "slow down"}}), RetryableLLMError),
        (genai_errors.APIError(503, {"error": {"message": "busy"}}), RetryableLLMError),
        (genai_errors.APIError(404, {"error": {"message": "no model"}}), FatalLLMError),
    ],
)
async def test_gemini_failures(result, error):
    client, _ = gemini_client(result)
    with pytest.raises(error):
        await call(GeminiVertexAdapter(client), "gemini-3.8-flash")


def test_claude_reads_quintessa_api_key_first(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-anthropic")
    monkeypatch.setenv("QUINTESSA_ANTHROPIC_API_KEY", "from-quintessa")
    assert ClaudeAdapter().client.api_key == "from-quintessa"
    monkeypatch.delenv("QUINTESSA_ANTHROPIC_API_KEY")
    assert ClaudeAdapter().client.api_key == "from-anthropic"
