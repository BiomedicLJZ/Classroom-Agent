# tests/test_auth.py
import json
from unittest.mock import MagicMock, patch

import pytest

from ta.config import Settings
from ta.google_auth import SCOPES, get_credentials


class TestSettings:
    def test_loads_nvidia_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        monkeypatch.setenv("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET_PATH", "credentials/client_secret.json")
        monkeypatch.setenv("GOOGLE_TOKEN_PATH", "credentials/token.json")
        settings = Settings()
        assert settings.nvidia_api_key == "nvapi-test"
        assert settings.nvidia_model == "meta/llama-3.3-70b-instruct"

    def test_raises_if_nvidia_key_missing(self, monkeypatch):
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        with pytest.raises(Exception):  # noqa: B017
            Settings()

    def test_reasoning_defaults(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        settings = Settings()
        assert settings.nvidia_temperature == 1.0
        assert settings.nvidia_top_p == 0.95
        assert settings.nvidia_max_tokens == 16384
        assert settings.nvidia_reasoning_budget == 16384
        assert settings.nvidia_enable_thinking is True

    def test_reasoning_overridable_from_env(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        monkeypatch.setenv("NVIDIA_TEMPERATURE", "0.3")
        monkeypatch.setenv("NVIDIA_ENABLE_THINKING", "false")
        settings = Settings()
        assert settings.nvidia_temperature == 0.3
        assert settings.nvidia_enable_thinking is False


class TestScopes:
    def test_scopes_include_topics_and_materials(self):
        assert "https://www.googleapis.com/auth/classroom.topics" in SCOPES
        assert "https://www.googleapis.com/auth/classroom.courseworkmaterials" in SCOPES


class TestGetCredentials:
    def _mock_settings(self, mock_settings_cls, secret_path: str, token_path: str):
        mock_account = MagicMock()
        mock_account.client_secret_path = secret_path
        mock_account.token_path = token_path
        mock_settings_cls.return_value.accounts = {"cugdl": mock_account, "uniat": MagicMock()}

    def test_loads_from_existing_valid_token(self, tmp_path):
        token_data = {
            "token": "ya29.fake",
            "refresh_token": "1//fake",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "fake.apps.googleusercontent.com",
            "client_secret": "fake-secret",
            "scopes": SCOPES,
        }
        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps(token_data))

        mock_creds = MagicMock()
        mock_creds.valid = True

        with (
            patch("ta.google_auth.Settings") as mock_settings_cls,
            patch("ta.google_auth.Credentials.from_authorized_user_file", return_value=mock_creds),
        ):
            self._mock_settings(mock_settings_cls, "fake_secret.json", str(token_file))
            creds = get_credentials("cugdl")

        assert creds is mock_creds

    def test_refresh_error_triggers_browser_flow(self, tmp_path):
        from google.auth.exceptions import RefreshError

        token_file = tmp_path / "token.json"
        token_file.write_text("{}")

        stale = MagicMock(valid=False, expired=True, refresh_token="1//x")
        stale.refresh.side_effect = RefreshError("invalid_grant: revoked")
        fresh = MagicMock(valid=True)
        fresh.to_json.return_value = '{"token": "new"}'

        with (
            patch("ta.google_auth.Settings") as mock_settings_cls,
            patch("ta.google_auth.Credentials.from_authorized_user_file", return_value=stale),
            patch("ta.google_auth.Request"),
            patch("ta.google_auth.InstalledAppFlow") as mock_flow_cls,
        ):
            mock_flow_cls.from_client_secrets_file.return_value.run_local_server.return_value = fresh
            self._mock_settings(mock_settings_cls, "fake_secret.json", str(token_file))
            creds = get_credentials("cugdl")

        assert creds is fresh
        assert token_file.read_text() == '{"token": "new"}'

    def test_refreshes_expired_token(self, tmp_path):
        token_file = tmp_path / "token.json"
        token_file.write_text("{}")

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "1//fake"
        mock_creds.to_json.return_value = "{}"

        with (
            patch("ta.google_auth.Settings") as mock_settings_cls,
            patch("ta.google_auth.Credentials.from_authorized_user_file", return_value=mock_creds),
            patch("ta.google_auth.Request") as mock_request,
        ):
            self._mock_settings(mock_settings_cls, "fake_secret.json", str(token_file))
            get_credentials("cugdl")
            mock_creds.refresh.assert_called_once_with(mock_request())
