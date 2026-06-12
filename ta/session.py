# ta/session.py
# Module-level active account state for the CLI session.
# Single-user process — no thread-safety needed.

_active_account: str = "cugdl"


def get_active_account() -> str:
    """Return the alias of the currently active Google account."""
    return _active_account


def set_active_account(alias: str) -> None:
    """Set the active Google account for all subsequent tool calls."""
    global _active_account
    _active_account = alias
