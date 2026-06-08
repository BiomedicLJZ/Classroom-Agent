# ta/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    nvidia_api_key: str
    nvidia_model: str = "nvidia/nemotron-3-ultra-550b-a55b"
    google_client_secret_path: str = "credentials/client_secret.json"
    google_token_path: str = "credentials/token.json"
