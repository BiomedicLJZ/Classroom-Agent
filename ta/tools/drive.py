# ta/tools/drive.py
import io
from functools import lru_cache

from googleapiclient.discovery import build
from langchain_core.tools import tool

from ta.config import Settings
from ta.google_auth import get_credentials

_GOOGLE_DOC_MIMES = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}
_TEXT_MIMES = {
    "text/plain", "text/x-python", "text/markdown",
    "text/x-markdown", "application/json", "text/html",
}


@lru_cache(maxsize=1)
def _drive_service():
    settings = Settings()
    creds = get_credentials(settings.google_client_secret_path, settings.google_token_path)
    return build("drive", "v3", credentials=creds)


@tool
def get_drive_file_text(file_id: str) -> str:
    """Download and return text content of a Google Drive file.
    Supports: Google Docs/Sheets/Slides (exported as text), Python/text/markdown files,
    PDFs (first 10 pages via pypdf)."""
    svc = _drive_service()
    meta = svc.files().get(fileId=file_id, fields="mimeType,name").execute()
    mime = meta.get("mimeType", "")

    if mime in _GOOGLE_DOC_MIMES:
        data = svc.files().export_media(fileId=file_id, mimeType=_GOOGLE_DOC_MIMES[mime]).execute()
        return data.decode("utf-8") if isinstance(data, bytes) else str(data)

    if mime in _TEXT_MIMES or mime.startswith("text/"):
        data = svc.files().get_media(fileId=file_id).execute()
        return data.decode("utf-8") if isinstance(data, bytes) else str(data)

    if mime == "application/pdf":
        from pypdf import PdfReader
        data = svc.files().get_media(fileId=file_id).execute()
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(p.extract_text() or "" for p in reader.pages[:10])

    return f"[Cannot read file type: {mime}. File name: {meta.get('name', 'unknown')}]"


@tool
def upload_file_to_drive(local_path: str, parent_folder_id: str, filename: str) -> str:
    """Upload a local file to a Google Drive folder. Returns the new file ID."""
    from googleapiclient.http import MediaFileUpload
    svc = _drive_service()
    result = svc.files().create(
        body={"name": filename, "parents": [parent_folder_id]},
        media_body=MediaFileUpload(local_path, resumable=True),
        fields="id",
    ).execute()
    return f"Uploaded '{filename}' to Drive (id: {result['id']})."
