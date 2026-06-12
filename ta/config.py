# ta/config.py
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class AccountConfig(BaseModel):
    client_secret_path: str
    token_path: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    nvidia_api_key: str
    nvidia_model: str = "nvidia/nemotron-3-ultra-550b-a55b"

    # CUGDL account (existing)
    google_client_secret_path: str = "credentials/client_secret.json"
    google_token_path: str = "credentials/token.json"

    # UNIAT account — add to .env when credentials are ready:
    #   UNIAT_CLIENT_SECRET_PATH=credentials/uniat_client_secret.json
    #   UNIAT_TOKEN_PATH=credentials/uniat_token.json
    uniat_client_secret_path: str = "credentials/uniat_client_secret.json"
    uniat_token_path: str = "credentials/uniat_token.json"

    @property
    def accounts(self) -> dict[str, AccountConfig]:
        return {
            "cugdl": AccountConfig(
                client_secret_path=self.google_client_secret_path,
                token_path=self.google_token_path,
            ),
            "uniat": AccountConfig(
                client_secret_path=self.uniat_client_secret_path,
                token_path=self.uniat_token_path,
            ),
        }
