# ta/session.py
# Module-level active account state for the CLI session.
# Single-user process — no thread-safety needed.

_active_account: str | None = None


def get_active_account() -> str:
    """Return the alias of the currently active Google account."""
    global _active_account
    if _active_account is None:
        from ta.config import Settings
        available = list(Settings().accounts.keys())
        if not available:
            # Fallback for bootstrap/tests if no credentials folder yet
            return "cugdl"
        _active_account = available[0]
    return _active_account


def set_active_account(alias: str) -> None:
    """Set the active Google account for all subsequent tool calls."""
    global _active_account
    _active_account = alias
