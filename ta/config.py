# ta/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    nvidia_api_key: str
    nvidia_model: str = "meta/llama-3.3-70b-instruct"
    google_client_secret_path: str = "credentials/client_secret.json"
    google_token_path: str = "credentials/token.json"
