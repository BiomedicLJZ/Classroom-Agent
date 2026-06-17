# ta/config.py
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class AccountConfig(BaseModel):
    client_secret_path: str
    token_path: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    nvidia_api_key: str = ""
    nvidia_model: str = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
    nvidia_temperature: float = 0.6
    nvidia_top_p: float = 0.95
    nvidia_max_tokens: int = 65536
    nvidia_reasoning_budget: int = 16384
    # Reasoning ON by default — this model only calls tools reliably with thinking
    # enabled; in multi-turn conversations tool-calling collapses to 0 when it is
    # off (verified). Toggle per-session with /think off, or set
    # NVIDIA_ENABLE_THINKING=false in .env to default it off.
    nvidia_enable_thinking: bool = True

    # Google Gemini Settings
    google_api_key: str = ""
    google_model: str = "gemini-3.5-flash"
    google_temperature: float = 0.7

    # LLM Provider Selection: 'nvidia' or 'google'
    llm_provider: str = "nvidia"

    # Provider for the content/curriculum generation subagents (content_agent,
    # planning_agent). Gemini handles long-form material generation well and calls
    # tools reliably without a thinking toggle. Falls back to llm_provider when the
    # chosen provider's API key is missing.
    content_provider: str = "google"

    # CUGDL account (existing)
    google_client_secret_path: str = "credentials/client_secret.json"
    google_token_path: str = "credentials/token.json"

    # Local Workspace
    base_workspace_path: str = "workspace/courses"

    # UNIAT account — add to .env when credentials are ready:
    #   UNIAT_CLIENT_SECRET_PATH=credentials/UNIAT.json
    #   UNIAT_TOKEN_PATH=credentials/uniat_token.json
    uniat_client_secret_path: str = "credentials/UNIAT.json"
    uniat_token_path: str = "credentials/uniat_token.json"

    @property
    def accounts(self) -> dict[str, AccountConfig]:
        import json
        from pathlib import Path
        
        creds_dir = Path("credentials")
        mapping_path = creds_dir / "accounts.json"
        
        if mapping_path.exists():
            try:
                with mapping_path.open() as f:
                    data = json.load(f)
                    return {k: AccountConfig(**v) for k, v in data.items()}
            except Exception:
                pass # Fallback to discovery if JSON is malformed
        
        # Discovery/Fallback logic
        accounts = {}
        
        # Legacy/Default CUGDL
        if Path(self.google_client_secret_path).exists():
            accounts["cugdl"] = AccountConfig(
                client_secret_path=self.google_client_secret_path,
                token_path=self.google_token_path,
            )
            
        # Legacy/Default UNIAT
        if Path(self.uniat_client_secret_path).exists():
            accounts["uniat"] = AccountConfig(
                client_secret_path=self.uniat_client_secret_path,
                token_path=self.uniat_token_path,
            )
            
        # Generic Discovery: scan credentials/ for client_secret_*.json
        for p in creds_dir.glob("client_secret_*.json"):
            alias = p.stem.replace("client_secret_", "")
            if alias and alias not in accounts:
                accounts[alias] = AccountConfig(
                    client_secret_path=str(p),
                    token_path=str(creds_dir / f"token_{alias}.json")
                )
                
        return accounts
