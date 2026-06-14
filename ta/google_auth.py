# ta/google_auth.py
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from ta.config import Settings

SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.students",
    "https://www.googleapis.com/auth/classroom.coursework.me",
    "https://www.googleapis.com/auth/classroom.announcements",
    "https://www.googleapis.com/auth/classroom.topics",
    "https://www.googleapis.com/auth/classroom.courseworkmaterials",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.students.readonly",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]


def get_credentials(alias: str) -> Credentials:
    """Load OAuth2 credentials for account alias, refreshing or triggering browser
    flow as needed. alias must match a key in Settings.accounts ('cugdl' or 'uniat')."""
    settings = Settings()
    if alias not in settings.accounts:
        raise ValueError(
            f"Unknown account alias '{alias}'. "
            f"Available: {list(settings.accounts.keys())}"
        )
    account = settings.accounts[alias]
    client_secret_path = account.client_secret_path
    token_path = account.token_path

    creds = None
    if Path(token_path).exists():
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        refreshed = False
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                refreshed = True
            except RefreshError:
                # Token revoked or scopes changed — discard and re-run consent.
                Path(token_path).unlink(missing_ok=True)
                creds = None
        if not refreshed:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
            creds = flow.run_local_server(port=0)
        Path(token_path).write_text(creds.to_json())

    return creds
