# ta/tools/docs.py
from functools import cache

from googleapiclient.discovery import build
from langchain_core.tools import tool
from langgraph.types import interrupt

from ta.google_auth import get_credentials
from ta.session import get_active_account


@cache
def _docs_service(alias: str):
    creds = get_credentials(alias)
    return build("docs", "v1", credentials=creds)


@tool
def get_doc_text(document_id: str) -> str:
    """Return the full plain text content of a Google Docs document."""
    svc = _docs_service(get_active_account())
    doc = svc.documents().get(documentId=document_id).execute()
    texts = []
    for element in doc.get("body", {}).get("content", []):
        if "paragraph" in element:
            for pe in element["paragraph"].get("elements", []):
                if "textRun" in pe:
                    texts.append(pe["textRun"].get("content", ""))
    return "".join(texts)


@tool
def add_doc_comment(document_id: str, anchor_text: str, comment_text: str) -> str:
    """Add a comment to a Google Docs document anchored to a specific text passage.
    Requires confirmation. anchor_text must be an exact substring of the document."""
    confirmed = interrupt({
        "action": "add_doc_comment",
        "details": (
            f"Add comment to doc {document_id}\n"
            f"Anchor: '{anchor_text[:80]}'\nComment: '{comment_text[:120]}'"
        ),
    })
    if not confirmed:
        return "Comment cancelled."

    svc = _docs_service(get_active_account())
    doc = svc.documents().get(documentId=document_id).execute()
    char_offset = 0
    anchor_start = None
    for element in doc.get("body", {}).get("content", []):
        if "paragraph" in element:
            for pe in element["paragraph"].get("elements", []):
                if "textRun" in pe:
                    run_text = pe["textRun"].get("content", "")
                    idx = run_text.find(anchor_text)
                    if idx != -1 and anchor_start is None:
                        anchor_start = char_offset + idx
                    char_offset += len(run_text)

    if anchor_start is None:
        return f"Anchor text '{anchor_text[:40]}' not found in document. Comment not added."

    from ta.tools.drive import _drive_service
    drive_svc = _drive_service(get_active_account())
    anchor_end = anchor_start + len(anchor_text)
    try:
        result = drive_svc.comments().create(
            fileId=document_id,
            body={
                "content": comment_text,
                "anchor": f'{{"r": [{{"startIndex": {anchor_start}, "endIndex": {anchor_end}}}]}}',
            },
            fields="id",
        ).execute()
        return f"Comment added (id: {result['id']})."
    except Exception as exc:
        return f"Comment posting note: {exc}"
