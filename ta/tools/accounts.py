# ta/tools/accounts.py
from langchain_core.tools import tool

from ta.config import Settings
from ta.session import get_active_account, set_active_account


@tool
def list_accounts() -> str:
    """List all configured Google accounts and show which one is currently active."""
    settings = Settings()
    active = get_active_account()
    lines = []
    for alias, cfg in settings.accounts.items():
        marker = "● (active)" if alias == active else "○"
        lines.append(f"  {marker} {alias}: {cfg.client_secret_path}")
    return "Configured Google accounts:\n" + "\n".join(lines)


@tool
def switch_account(alias: str) -> str:
    """Switch the active Google account for all subsequent Classroom, Drive, and Docs operations."""
    settings = Settings()
    available = list(settings.accounts.keys())
    if alias not in available:
        return f"Unknown account '{alias}'. Available: {available}"
    set_active_account(alias)
    return f"Switched to account: '{alias}'. All subsequent operations will use this account."


@tool
def register_account(alias: str, client_secret_path: str) -> str:
    """Register a new Google account with a custom alias and its client_secret.json path.
    This persists the mapping to credentials/accounts.json."""
    import json
    from pathlib import Path

    from ta.config import AccountConfig
    
    creds_dir = Path("credentials")
    creds_dir.mkdir(parents=True, exist_ok=True)
    
    secret_p = Path(client_secret_path)
    if not secret_p.exists():
        return f"ERROR: client_secret file not found at '{client_secret_path}'"
        
    mapping_path = creds_dir / "accounts.json"
    settings = Settings()
    accounts = settings.accounts 
    
    # Update or add
    token_p = creds_dir / f"token_{alias}.json"
    accounts[alias] = AccountConfig(
        client_secret_path=str(secret_p.resolve()),
        token_path=str(token_p.resolve())
    )
    
    # Save back to JSON
    data = {k: v.model_dump() for k, v in accounts.items()}
    with mapping_path.open("w") as f:
        json.dump(data, f, indent=2)
        
    return f"SUCCESS: Account '{alias}' registered. You can now use switch_account('{alias}')."
