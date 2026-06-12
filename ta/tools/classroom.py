# ta/tools/classroom.py
import json
from functools import lru_cache

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from langchain_core.tools import tool
from langgraph.types import interrupt

from ta.google_auth import get_credentials
from ta.session import get_active_account


def _http_error_msg(exc: HttpError, course_id: str = "", resource: str = "") -> str:
    """Return a helpful string for common Classroom API HTTP errors."""
    status = exc.resp.status
    if status == 404:
        target = resource or (f"course {course_id}" if course_id else "resource")
        return (
            f"Not found: {target} does not exist or is not accessible with the active account. "
            "Run list_courses() to confirm the correct course ID and active account."
        )
    if status == 403:
        return "Permission denied. Check that the active account has Teacher/Owner access."
    return f"Google API error {status}: {exc.reason}"


@lru_cache(maxsize=None)
def _classroom_service(alias: str):
    creds = get_credentials(alias)
    return build("classroom", "v1", credentials=creds)


@tool
def list_courses() -> str:
    """List all active Google Classroom courses the authenticated user has access to."""
    svc = _classroom_service(get_active_account())
    response = svc.courses().list(courseStates=["ACTIVE"]).execute()
    courses = response.get("courses", [])
    if not courses:
        return "No active courses found."
    lines = [f"- [{c['id']}] {c.get('name', 'Unnamed')} — {c.get('section', '')}" for c in courses]
    return "Active courses:\n" + "\n".join(lines)


@tool
def list_students(course_id: str) -> str:
    """List all enrolled students in a Google Classroom course."""
    svc = _classroom_service(get_active_account())
    response = svc.courses().students().list(courseId=course_id).execute()
    students = response.get("students", [])
    if not students:
        return f"No students found in course {course_id}."
    lines = []
    for s in students:
        profile = s.get("profile", {})
        name = profile.get("name", {}).get("fullName", "Unknown")
        email = profile.get("emailAddress", "")
        lines.append(f"- [{s['userId']}] {name} <{email}>")
    return f"Students ({len(lines)}):\n" + "\n".join(lines)


@tool
def list_assignments(course_id: str) -> str:
    """List all coursework (assignments, quizzes) in a Google Classroom course."""
    svc = _classroom_service(get_active_account())
    response = svc.courses().courseWork().list(courseId=course_id).execute()
    items = response.get("courseWork", [])
    if not items:
        return f"No assignments found in course {course_id}."
    lines = [
        f"- [{cw['id']}] {cw.get('title', 'Untitled')} (max: {cw.get('maxPoints', 'N/A')} pts)"
        for cw in items
    ]
    return "Assignments:\n" + "\n".join(lines)


@tool
def get_submission_status(course_id: str, coursework_id: str) -> str:
    """Return submission state for every student in an assignment.
    States: NEW, CREATED, TURNED_IN, RETURNED, RECLAIMED_BY_STUDENT."""
    svc = _classroom_service(get_active_account())
    response = (
        svc.courses().courseWork().studentSubmissions()
        .list(courseId=course_id, courseWorkId=coursework_id)
        .execute()
    )
    subs = response.get("studentSubmissions", [])
    if not subs:
        return "No submissions found."
    lines = [f"- [{s['userId']}] Submission {s['id']}: {s.get('state', 'UNKNOWN')}" for s in subs]
    return f"Submission status ({len(lines)} students):\n" + "\n".join(lines)


@tool
def get_submission(course_id: str, coursework_id: str, submission_id: str) -> str:
    """Fetch a single student submission including attached Drive file IDs."""
    svc = _classroom_service(get_active_account())
    sub = (
        svc.courses().courseWork().studentSubmissions()
        .get(courseId=course_id, courseWorkId=coursework_id, id=submission_id)
        .execute()
    )
    attachments = [
        a["driveFile"].get("id", "unknown")
        for a in sub.get("assignmentSubmission", {}).get("attachments", [])
        if "driveFile" in a
    ]
    return json.dumps({
        "submission_id": sub["id"],
        "student_id": sub["userId"],
        "state": sub.get("state"),
        "drive_file_ids": attachments,
        "late": sub.get("late", False),
    }, indent=2)


@tool
def post_announcement(course_id: str, text: str) -> str:
    """Post a plain-text announcement to a Google Classroom course. Requires confirmation."""
    confirmed = interrupt({
        "action": "post_announcement",
        "details": f"Post announcement to course {course_id}:\n\n{text}",
    })
    if not confirmed:
        return "Announcement posting cancelled."
    svc = _classroom_service(get_active_account())
    try:
        result = svc.courses().announcements().create(
            courseId=course_id, body={"text": text, "state": "PUBLISHED"}
        ).execute()
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id)
    return f"Announcement posted (id: {result['id']})."


@tool
def create_assignment(
    course_id: str,
    title: str,
    description: str,
    max_points: float,
    due_date: str,
    due_time: str,
    materials_drive_ids: list[str],
) -> str:
    """Create a new assignment in a Google Classroom course. Requires confirmation.
    due_date: YYYY-MM-DD format. due_time: HH:MM (24h)."""
    confirmed = interrupt({
        "action": "create_assignment",
        "details": (
            f"Create assignment '{title}' in course {course_id}\n"
            f"Max points: {max_points}, Due: {due_date} {due_time}\n\n"
            f"Description:\n{description}"
        ),
    })
    if not confirmed:
        return "Assignment creation cancelled."
    year, month, day = map(int, due_date.split("-"))
    hour, minute = map(int, due_time.split(":"))
    body: dict = {
        "title": title, "description": description, "maxPoints": max_points,
        "workType": "ASSIGNMENT", "state": "PUBLISHED",
        "dueDate": {"year": year, "month": month, "day": day},
        "dueTime": {"hours": hour, "minutes": minute},
    }
    if materials_drive_ids:
        body["materials"] = [
            {"driveFile": {"driveFile": {"id": fid}, "shareMode": "VIEW"}}
            for fid in materials_drive_ids
        ]
    svc = _classroom_service(get_active_account())
    try:
        result = svc.courses().courseWork().create(courseId=course_id, body=body).execute()
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id)
    return f"Assignment created (id: {result['id']}, title: {result.get('title')})."


@tool
def invite_user(course_id: str, user_email: str, role: str) -> str:
    """Invite a user to a Google Classroom course. role must be 'STUDENT' or 'TEACHER'.
    Requires confirmation before sending."""
    role_upper = role.upper()
    if role_upper not in ("STUDENT", "TEACHER"):
        return f"Invalid role '{role}'. Must be STUDENT or TEACHER."
    confirmed = interrupt({
        "action": "invite_user",
        "details": f"Invite {user_email} to course {course_id} as {role_upper}",
    })
    if not confirmed:
        return "Invitation cancelled."
    svc = _classroom_service(get_active_account())
    try:
        result = svc.invitations().create(
            body={"courseId": course_id, "userId": user_email, "role": role_upper}
        ).execute()
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id, resource=f"user {user_email}")
    return f"Invitation sent (id: {result['id']}) — {user_email} invited as {role_upper}."


@tool
def list_invitations(course_id: str) -> str:
    """List all pending invitations for a Google Classroom course."""
    svc = _classroom_service(get_active_account())
    response = svc.invitations().list(courseId=course_id).execute()
    invitations = response.get("invitations", [])
    if not invitations:
        return f"No pending invitations for course {course_id}."
    lines = [
        f"- [{inv['id']}] {inv.get('userId', 'unknown')} as {inv.get('role', 'unknown')}"
        for inv in invitations
    ]
    return f"Pending invitations ({len(lines)}):\n" + "\n".join(lines)


@tool
def delete_invitation(invitation_id: str) -> str:
    """Cancel and delete a pending Google Classroom invitation by its ID. Requires confirmation."""
    confirmed = interrupt({
        "action": "delete_invitation",
        "details": f"Delete invitation {invitation_id}",
    })
    if not confirmed:
        return "Invitation deletion cancelled."
    svc = _classroom_service(get_active_account())
    try:
        svc.invitations().delete(id=invitation_id).execute()
    except HttpError as exc:
        return _http_error_msg(exc, resource=f"invitation {invitation_id}")
    return f"Invitation {invitation_id} deleted."


@tool
def create_material(
    course_id: str,
    title: str,
    description: str,
    drive_file_ids: list[str],
    youtube_urls: list[str],
    link_urls: list[str],
) -> str:
    """Post study materials (Drive files, YouTube, links) to a course. Requires confirmation."""
    confirmed = interrupt({
        "action": "create_material",
        "details": (
            f"Post material '{title}' to course {course_id}\n\n"
            f"Description:\n{description}"
        ),
    })
    if not confirmed:
        return "Material posting cancelled."
    materials = []
    for fid in drive_file_ids:
        materials.append({"driveFile": {"driveFile": {"id": fid}, "shareMode": "VIEW"}})
    for url in youtube_urls:
        video_id = url.split("v=")[-1].split("&")[0]
        materials.append({"youtubeVideo": {"id": video_id}})
    for url in link_urls:
        materials.append({"link": {"url": url}})
    svc = _classroom_service(get_active_account())
    try:
        result = svc.courses().courseWorkMaterials().create(
            courseId=course_id,
            body={
                "title": title,
                "description": description,
                "materials": materials,
                "state": "PUBLISHED",
            },
        ).execute()
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id)
    return f"Material posted (id: {result['id']})."


@tool
def update_assignment(
    course_id: str,
    coursework_id: str,
    title: str = "",
    description: str = "",
    due_date: str = "",
    due_time: str = "",
    max_points: float = -1,
    state: str = "",
    topic_id: str = "",
) -> str:
    """Update fields of an existing assignment. Only provided (non-empty) fields change.
    due_date: YYYY-MM-DD. due_time: HH:MM (24h). state: PUBLISHED or DRAFT.
    topic_id: assign the coursework to a topic (see list_topics). Requires confirmation."""
    body: dict = {}
    mask: list[str] = []
    if title:
        body["title"] = title
        mask.append("title")
    if description:
        body["description"] = description
        mask.append("description")
    if due_date:
        year, month, day = map(int, due_date.split("-"))
        body["dueDate"] = {"year": year, "month": month, "day": day}
        mask.append("dueDate")
    if due_time:
        hour, minute = map(int, due_time.split(":"))
        body["dueTime"] = {"hours": hour, "minutes": minute}
        mask.append("dueTime")
    if max_points >= 0:
        body["maxPoints"] = max_points
        mask.append("maxPoints")
    if state:
        body["state"] = state.upper()
        mask.append("state")
    if topic_id:
        body["topicId"] = topic_id
        mask.append("topicId")
    if not mask:
        return "Nothing to update — provide at least one field."
    details = f"Update assignment {coursework_id} in course {course_id}\nFields: {', '.join(mask)}"
    if description:
        details += f"\n\nNew description:\n{description}"
    confirmed = interrupt({"action": "update_assignment", "details": details})
    if not confirmed:
        return "Assignment update cancelled."
    svc = _classroom_service(get_active_account())
    try:
        result = (
            svc.courses().courseWork()
            .patch(
                courseId=course_id, id=coursework_id,
                updateMask=",".join(mask), body=body,
            )
            .execute()
        )
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id, resource=f"assignment {coursework_id}")
    return f"Assignment {result['id']} updated ({', '.join(mask)})."


@tool
def delete_assignment(course_id: str, coursework_id: str) -> str:
    """Permanently delete an assignment and its submissions. Requires confirmation."""
    confirmed = interrupt({
        "action": "delete_assignment",
        "details": f"PERMANENTLY delete assignment {coursework_id} from course {course_id}",
    })
    if not confirmed:
        return "Assignment deletion cancelled."
    svc = _classroom_service(get_active_account())
    try:
        svc.courses().courseWork().delete(courseId=course_id, id=coursework_id).execute()
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id, resource=f"assignment {coursework_id}")
    return f"Assignment {coursework_id} deleted."


@tool
def list_announcements(course_id: str) -> str:
    """List announcements in a course with their IDs, newest first."""
    svc = _classroom_service(get_active_account())
    try:
        response = svc.courses().announcements().list(
            courseId=course_id, orderBy="updateTime desc", pageSize=20
        ).execute()
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id)
    items = response.get("announcements", [])
    if not items:
        return f"No announcements in course {course_id}."
    lines = [
        f"- [{a['id']}] ({a.get('state', '?')}) {a.get('text', '')[:80]}" for a in items
    ]
    return f"Announcements ({len(lines)}):\n" + "\n".join(lines)


@tool
def update_announcement(
    course_id: str, announcement_id: str, text: str = "", state: str = ""
) -> str:
    """Update an announcement's text and/or state (PUBLISHED or DRAFT).
    Only provided (non-empty) fields change. Requires confirmation."""
    body: dict = {}
    mask: list[str] = []
    if text:
        body["text"] = text
        mask.append("text")
    if state:
        body["state"] = state.upper()
        mask.append("state")
    if not mask:
        return "Nothing to update — provide text and/or state."
    details = f"Update announcement {announcement_id} in course {course_id}"
    if text:
        details += f"\n\nNew text:\n{text}"
    confirmed = interrupt({"action": "update_announcement", "details": details})
    if not confirmed:
        return "Announcement update cancelled."
    svc = _classroom_service(get_active_account())
    try:
        result = (
            svc.courses().announcements()
            .patch(
                courseId=course_id, id=announcement_id,
                updateMask=",".join(mask), body=body,
            )
            .execute()
        )
    except HttpError as exc:
        return _http_error_msg(
            exc, course_id=course_id, resource=f"announcement {announcement_id}"
        )
    return f"Announcement {result['id']} updated."


@tool
def delete_announcement(course_id: str, announcement_id: str) -> str:
    """Permanently delete an announcement. Requires confirmation."""
    confirmed = interrupt({
        "action": "delete_announcement",
        "details": f"PERMANENTLY delete announcement {announcement_id} from course {course_id}",
    })
    if not confirmed:
        return "Announcement deletion cancelled."
    svc = _classroom_service(get_active_account())
    try:
        svc.courses().announcements().delete(courseId=course_id, id=announcement_id).execute()
    except HttpError as exc:
        return _http_error_msg(
            exc, course_id=course_id, resource=f"announcement {announcement_id}"
        )
    return f"Announcement {announcement_id} deleted."


@tool
def list_materials(course_id: str) -> str:
    """List courseWork materials in a course with their IDs."""
    svc = _classroom_service(get_active_account())
    try:
        response = svc.courses().courseWorkMaterials().list(
            courseId=course_id, pageSize=20
        ).execute()
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id)
    items = response.get("courseWorkMaterial", [])
    if not items:
        return f"No materials in course {course_id}."
    lines = [
        f"- [{m['id']}] ({m.get('state', '?')}) {m.get('title', 'Untitled')}" for m in items
    ]
    return f"Materials ({len(lines)}):\n" + "\n".join(lines)


@tool
def update_material(
    course_id: str, material_id: str, title: str = "", description: str = ""
) -> str:
    """Update a material's title and/or description. Only provided (non-empty)
    fields change. Requires confirmation."""
    body: dict = {}
    mask: list[str] = []
    if title:
        body["title"] = title
        mask.append("title")
    if description:
        body["description"] = description
        mask.append("description")
    if not mask:
        return "Nothing to update — provide title and/or description."
    details = f"Update material {material_id} in course {course_id}"
    if description:
        details += f"\n\nNew description:\n{description}"
    confirmed = interrupt({"action": "update_material", "details": details})
    if not confirmed:
        return "Material update cancelled."
    svc = _classroom_service(get_active_account())
    try:
        result = (
            svc.courses().courseWorkMaterials()
            .patch(
                courseId=course_id, id=material_id,
                updateMask=",".join(mask), body=body,
            )
            .execute()
        )
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id, resource=f"material {material_id}")
    return f"Material {result['id']} updated."


@tool
def delete_material(course_id: str, material_id: str) -> str:
    """Permanently delete a courseWork material. Requires confirmation."""
    confirmed = interrupt({
        "action": "delete_material",
        "details": f"PERMANENTLY delete material {material_id} from course {course_id}",
    })
    if not confirmed:
        return "Material deletion cancelled."
    svc = _classroom_service(get_active_account())
    try:
        svc.courses().courseWorkMaterials().delete(courseId=course_id, id=material_id).execute()
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id, resource=f"material {material_id}")
    return f"Material {material_id} deleted."
