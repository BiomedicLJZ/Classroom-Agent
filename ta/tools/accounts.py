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
    """Switch the active Google account for all subsequent Classroom, Drive, and Docs operations.
    Available aliases: 'cugdl', 'uniat'."""
    settings = Settings()
    available = list(settings.accounts.keys())
    if alias not in available:
        return f"Unknown account '{alias}'. Available: {available}"
    set_active_account(alias)
    return f"Switched to account: '{alias}'. All subsequent operations will use this account."
