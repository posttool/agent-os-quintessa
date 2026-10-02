from __future__ import annotations

from typing import Any

import httpx

DEFAULT_URL = "https://api.typesafe.ai"
DEFAULT_MODEL = "jev-latest"


class SystemOneError(Exception):
    pass


class SystemOneClient:
    """A client for `POST /v1/systemone`, the decision API TypeSafe's Jev
    serves and gev (github.com/dglazkov/gev) copies. Send a state and named
    questions (choice, score, noul); get typed answers with probabilities.
    Point `base_url` at a gev deployment to use the open-source model."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        if not api_key:
            raise SystemOneError("no API key for the System One endpoint")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport

    @property
    def label(self) -> str:
        host = self.base_url.split("://", 1)[-1]
        return self.model if host == DEFAULT_URL.split("://", 1)[1] else f"{self.model}@{host}"

    async def ask(self, state: Any, questions: dict[str, dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], str]:
        """Answers keyed by question name, and the model that answered."""
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as http:
            try:
                response = await http.post(
                    f"{self.base_url}/v1/systemone",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"state": state, "model": self.model, "questions": questions},
                )
            except httpx.HTTPError as e:
                raise SystemOneError(f"{type(e).__name__}: {e}") from e
        if response.status_code != 200:
            raise SystemOneError(f"HTTP {response.status_code}: {response.text[:200]}")
        data = response.json()
        return data.get("answers", {}), data.get("model", self.model)


def choice(instructions: str, criteria: dict[str, str | None]) -> dict[str, Any]:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}
