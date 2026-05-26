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


class TestGetCredentials:
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

        with patch("ta.google_auth.Credentials.from_authorized_user_file", return_value=mock_creds):
            creds = get_credentials("fake_secret.json", str(token_file))

        assert creds is mock_creds

    def test_refreshes_expired_token(self, tmp_path):
        token_file = tmp_path / "token.json"
        token_file.write_text("{}")

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "1//fake"
        mock_creds.to_json.return_value = "{}"

        with (
            patch("ta.google_auth.Credentials.from_authorized_user_file", return_value=mock_creds),
            patch("ta.google_auth.Request") as mock_request,
        ):
            get_credentials("fake_secret.json", str(token_file))
            mock_creds.refresh.assert_called_once_with(mock_request())
