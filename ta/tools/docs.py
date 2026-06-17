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


def _extract_text_runs(content_list: list, runs: list) -> None:
    for element in content_list:
        if "paragraph" in element:
            for pe in element["paragraph"].get("elements", []):
                if "textRun" in pe:
                    runs.append(pe)
        elif "table" in element:
            for row in element["table"].get("tableRows", []):
                for cell in row.get("tableCells", []):
                    _extract_text_runs(cell.get("content", []), runs)
        elif "tableOfContents" in element:
            _extract_text_runs(element["tableOfContents"].get("content", []), runs)


@tool
def get_doc_text(document_id: str) -> str:
    """Return the full plain text content of a Google Docs document."""
    svc = _docs_service(get_active_account())
    doc = svc.documents().get(documentId=document_id).execute()
    runs = []
    _extract_text_runs(doc.get("body", {}).get("content", []), runs)
    return "".join(pe["textRun"].get("content", "") for pe in runs)


@tool
def add_doc_comment(document_id: str, anchor_text: str, comment_text: str) -> str:
    """Add a comment to a Google Docs document anchored to a specific text passage.
    Requires confirmation. anchor_text must be an exact substring of the document."""
    if not anchor_text:
        return "Error: anchor_text cannot be empty."

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
    
    runs = []
    _extract_text_runs(doc.get("body", {}).get("content", []), runs)
    
    full_text = ""
    index_map = []
    for pe in runs:
        run_text = pe["textRun"].get("content", "")
        run_start = pe.get("startIndex")
        if run_start is not None:
            for i in range(len(run_text)):
                full_text += run_text[i]
                index_map.append(run_start + i)

    idx = full_text.find(anchor_text)
    if idx == -1:
        return f"Anchor text '{anchor_text[:40]}' not found in document. Comment not added."

    from ta.tools.drive import _drive_service
    drive_svc = _drive_service(get_active_account())
    anchor_start = index_map[idx]
    anchor_end = index_map[idx + len(anchor_text) - 1] + 1
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
