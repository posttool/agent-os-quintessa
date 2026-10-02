from __future__ import annotations

import json
import os
import tempfile

from quintessa.llm.errors import FatalLLMError

SA_JSON_VAR = "QUINTESSA_GCP_SA_JSON"


def load_service_account_env() -> None:
    """Let a Google service account key arrive as one environment variable.

    Hosted environments often take secrets only as variables, while Google's
    application default credentials want a file. When QUINTESSA_GCP_SA_JSON
    holds the key's JSON and GOOGLE_APPLICATION_CREDENTIALS is unset, write
    the key to a private file and point GOOGLE_APPLICATION_CREDENTIALS at it.
    GOOGLE_CLOUD_PROJECT defaults to the key's project. Safe to call again."""
    raw = os.environ.get(SA_JSON_VAR, "").strip()
    if not raw or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as e:
        raise FatalLLMError(f"{SA_JSON_VAR} is not valid JSON") from e
    if not isinstance(info, dict) or info.get("type") != "service_account":
        raise FatalLLMError(f"{SA_JSON_VAR} is not a service account key")
    fd, path = tempfile.mkstemp(prefix="quintessa-sa-", suffix=".json")  # created with mode 0600
    with os.fdopen(fd, "w") as f:
        json.dump(info, f)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path
    if info.get("project_id"):
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", info["project_id"])
