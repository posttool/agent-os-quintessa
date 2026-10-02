import json
import os
import stat

import pytest

from quintessa.llm.credentials import load_service_account_env
from quintessa.llm.errors import FatalLLMError

KEY = {"type": "service_account", "project_id": "demo-proj", "client_email": "a@b.iam.gserviceaccount.com"}


@pytest.fixture
def env(monkeypatch):
    for var in ("QUINTESSA_GCP_SA_JSON", "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_key_in_variable_becomes_private_credentials_file(env):
    env.setenv("QUINTESSA_GCP_SA_JSON", json.dumps(KEY))
    load_service_account_env()
    path = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
    try:
        assert json.load(open(path)) == KEY
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        assert os.environ["GOOGLE_CLOUD_PROJECT"] == "demo-proj"
    finally:
        os.remove(path)


def test_existing_settings_win(env):
    env.setenv("QUINTESSA_GCP_SA_JSON", json.dumps(KEY))
    env.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/elsewhere.json")
    load_service_account_env()
    assert os.environ["GOOGLE_APPLICATION_CREDENTIALS"] == "/elsewhere.json"
    assert "GOOGLE_CLOUD_PROJECT" not in os.environ


def test_project_variable_is_kept(env):
    env.setenv("QUINTESSA_GCP_SA_JSON", json.dumps(KEY))
    env.setenv("GOOGLE_CLOUD_PROJECT", "mine")
    load_service_account_env()
    os.remove(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
    assert os.environ["GOOGLE_CLOUD_PROJECT"] == "mine"


@pytest.mark.parametrize("raw", ["not json", json.dumps({"type": "authorized_user"})])
def test_bad_key_is_a_clear_error(env, raw):
    env.setenv("QUINTESSA_GCP_SA_JSON", raw)
    with pytest.raises(FatalLLMError, match="QUINTESSA_GCP_SA_JSON"):
        load_service_account_env()
