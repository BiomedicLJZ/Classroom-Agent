# ta/tools/grading.py
import json
import re
from functools import lru_cache
from pathlib import Path

import yaml
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langgraph.types import interrupt

from ta.config import Settings
from ta.session import get_active_account

GRADING_SYSTEM_PROMPT = """\
You are an expert teaching assistant grading student submissions.
Evaluate the submission against the provided rubric criteria.
Return ONLY valid JSON with this exact schema:
{
  "criteria_scores": {"CriteriaName": score_float},
  "score": total_float,
  "max_score": max_float,
  "feedback_text": "narrative feedback for the student",
  "inline_comments": []
}
Do not include any text outside the JSON object."""


@lru_cache(maxsize=1)
def _get_llm():
    settings = Settings()
    return ChatNVIDIA(
        model=settings.nvidia_model,
        api_key=settings.nvidia_api_key,
        temperature=settings.nvidia_temperature,
        top_p=settings.nvidia_top_p,
        max_tokens=settings.nvidia_max_tokens,
        reasoning_budget=settings.nvidia_reasoning_budget,
        chat_template_kwargs={"enable_thinking": settings.nvidia_enable_thinking},
    )


def _extract_json(text: str) -> str:
    """Strip <think> blocks and markdown code fences from LLM output."""
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    return match.group(1).strip() if match else text.strip()


def _as_text(content) -> str:
    """Normalize LLM content to a string — newer providers may return content blocks."""
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return content or ""


@tool
def load_rubric(rubric_path: str) -> str:
    """Load a grading rubric from a YAML file. Returns a JSON array of criteria objects."""
    path = Path(rubric_path)
    if not path.exists():
        return f"Error: Rubric file not found at '{rubric_path}'."
    with path.open() as f:
        data = yaml.safe_load(f)
    return json.dumps(data.get("criteria", []), indent=2)


@tool
def analyze_submission(submission_text: str, rubric_json: str, assignment_type: str) -> str:
    """Use the NVIDIA LLM to evaluate a student submission against a rubric.
    assignment_type: 'code' | 'report' | 'documentation' | 'diagram'
    Returns a JSON GradeResult."""
    llm = _get_llm()
    response = llm.invoke([
        SystemMessage(content=GRADING_SYSTEM_PROMPT),
        HumanMessage(content=(
            f"Assignment type: {assignment_type}\n\n"
            f"Rubric:\n{rubric_json}\n\n"
            f"Submission:\n```\n{submission_text[:8000]}\n```\n\n"
            "Return only the JSON grade result."
        )),
    ])
    parsed = json.loads(_extract_json(_as_text(response.content)))
    return json.dumps(parsed, indent=2)


@tool
def post_grade(
    course_id: str, coursework_id: str, student_id: str, score: float, private_comment: str
) -> str:
    """Post a numeric grade and private comment to a student's Classroom submission.
    Requires instructor confirmation."""
    confirmed = interrupt({
        "action": "post_grade",
        "details": (
            f"Post grade {score} pts to student {student_id}\n"
            f"Assignment: {coursework_id} in course {course_id}\n"
            f"Comment: {private_comment[:120]}"
        ),
    })
    if not confirmed:
        return f"Grade for student {student_id} cancelled."

    from googleapiclient.discovery import build

    from ta.google_auth import get_credentials
    creds = get_credentials(get_active_account())
    svc = build("classroom", "v1", credentials=creds)

    subs = (
        svc.courses().courseWork().studentSubmissions()
        .list(courseId=course_id, courseWorkId=coursework_id, userId=student_id)
        .execute()
    )
    submission_id = subs["studentSubmissions"][0]["id"]
    svc.courses().courseWork().studentSubmissions().patch(
        courseId=course_id, courseWorkId=coursework_id, id=submission_id,
        updateMask="assignedGrade,draftGrade",
        body={"assignedGrade": score, "draftGrade": score},
    ).execute()
    svc.courses().courseWork().studentSubmissions().return_(
        courseId=course_id, courseWorkId=coursework_id, body={"ids": [submission_id]}
    ).execute()
    return f"Grade {score} posted for student {student_id} (submission {submission_id})."


@tool
def post_private_comment(
    course_id: str, coursework_id: str, submission_id: str, comment_text: str
) -> str:
    """Add a private comment to a student's Classroom submission. Requires confirmation."""
    confirmed = interrupt({
        "action": "post_private_comment",
        "details": f"Add private comment to submission {submission_id}:\n{comment_text[:200]}",
    })
    if not confirmed:
        return "Private comment cancelled."
    from googleapiclient.discovery import build

    from ta.google_auth import get_credentials
    creds = get_credentials(get_active_account())
    svc = build("classroom", "v1", credentials=creds)
    svc.courses().courseWork().studentSubmissions().modifyAttachments(
        courseId=course_id, courseWorkId=coursework_id, id=submission_id,
        body={"addAttachments": []},
    ).execute()
    return f"Private comment added to submission {submission_id}."


@tool
def batch_grade_assignment(
    course_id: str, coursework_id: str, rubric_path: str, assignment_type: str
) -> str:
    """Grade ALL TURNED_IN submissions for an assignment using a YAML rubric.
    Fetches each submission's Drive files and analyzes with NVIDIA LLM.
    Returns a summary table. Grades are NOT posted — call post_grade for each student."""
    from ta.tools.classroom import _classroom_service
    from ta.tools.drive import get_drive_file_text

    rubric_json = load_rubric.invoke({"rubric_path": rubric_path})
    if rubric_json.startswith("Error"):
        return rubric_json

    svc = _classroom_service(get_active_account())
    subs_response = (
        svc.courses().courseWork().studentSubmissions()
        .list(courseId=course_id, courseWorkId=coursework_id)
        .execute()
    )
    turned_in = [
        s for s in subs_response.get("studentSubmissions", [])
        if s.get("state") == "TURNED_IN"
    ]
    if not turned_in:
        return "No TURNED_IN submissions found."

    lines = []
    for sub in turned_in:
        file_ids = [
            a["driveFile"]["id"]
            for a in sub.get("assignmentSubmission", {}).get("attachments", [])
            if "driveFile" in a
        ]
        submission_text = "\n".join(
            get_drive_file_text.invoke({"file_id": fid}) for fid in file_ids
        )
        if not submission_text.strip():
            lines.append(f"- Student {sub['userId']}: No readable file attached — skipped.")
            continue
        try:
            grade = json.loads(analyze_submission.invoke({
                "submission_text": submission_text,
                "rubric_json": rubric_json,
                "assignment_type": assignment_type,
            }))
            lines.append(
                f"- Student {sub['userId']}: {grade['score']}/{grade['max_score']} pts\n"
                f"  {grade['feedback_text'][:100]}..."
            )
        except Exception as exc:
            lines.append(f"- Student {sub['userId']}: Grading failed — {exc}")

    return (
        f"Grading complete ({len(turned_in)} submissions):\n"
        + "\n".join(lines)
        + "\n\nCall post_grade for each student to publish grades."
    )


@tool
def export_grades(course_id: str, output_path: str) -> str:
    """Export all grades for a course to an .xlsx file: one row per student, one
    column per assignment, cell = assignedGrade (empty when not graded yet)."""
    from openpyxl import Workbook

    from ta.tools.classroom import _classroom_service

    svc = _classroom_service(get_active_account())
    roster = svc.courses().students().list(courseId=course_id).execute().get("students", [])
    coursework = (
        svc.courses().courseWork().list(courseId=course_id).execute().get("courseWork", [])
    )
    if not roster:
        return f"No students in course {course_id}."
    if not coursework:
        return f"No coursework in course {course_id}."

    grades: dict[str, dict[str, float]] = {}
    for cw in coursework:
        subs = (
            svc.courses().courseWork().studentSubmissions()
            .list(courseId=course_id, courseWorkId=cw["id"])
            .execute()
            .get("studentSubmissions", [])
        )
        for sub in subs:
            if "assignedGrade" in sub:
                grades.setdefault(sub["userId"], {})[cw["id"]] = sub["assignedGrade"]

    wb = Workbook()
    ws = wb.active
    ws.title = "Grades"
    ws.append(["Student", "Email"] + [cw.get("title", cw["id"]) for cw in coursework])
    for student in roster:
        profile = student.get("profile", {})
        row = [
            profile.get("name", {}).get("fullName", "Unknown"),
            profile.get("emailAddress", ""),
        ]
        student_grades = grades.get(student["userId"], {})
        row += [student_grades.get(cw["id"]) for cw in coursework]
        ws.append(row)
    wb.save(output_path)
    return (
        f"Grades exported: {len(roster)} students × {len(coursework)} assignments "
        f"→ {output_path}"
    )
