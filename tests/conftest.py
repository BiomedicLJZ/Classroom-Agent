# tests/conftest.py
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_creds():
    creds = MagicMock()
    creds.valid = True
    creds.expired = False
    return creds


@pytest.fixture(autouse=True)
def set_required_env_vars(monkeypatch, tmp_path):
    """Ensure required env vars are set in every test.
    chdir to tmp_path so pydantic-settings finds no real .env file and
    reads only from the env vars we explicitly set here."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")
    monkeypatch.setenv("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET_PATH", "credentials/client_secret.json")
    monkeypatch.setenv("GOOGLE_TOKEN_PATH", "credentials/token.json")
