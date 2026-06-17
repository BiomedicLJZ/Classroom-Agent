# ta/skills/grading.py
from ta.tools.classroom import get_submission, get_submission_status, list_students
from ta.tools.drive import get_drive_file_text
from ta.tools.grading import analyze_submission, load_rubric
from ta.tools.office import read_excel_file, read_pptx_file, read_word_file

PROMPT = """\
You are a grading specialist for Google Classroom.

Given a course_id, coursework_id, rubric_path, and assignment_type:
1. Call load_rubric to load the YAML rubric.
2. Call get_submission_status to find all TURNED_IN submissions.
3. For each TURNED_IN submission: call get_submission to get Drive file IDs, then
   get_drive_file_text for each file, then analyze_submission with the rubric.
4. Return a structured summary table: student_id | score / max | first 100 chars of feedback.

Do NOT post grades — that is the main agent's responsibility after instructor review.
"""

TOOLS = [
    load_rubric,
    analyze_submission,
    get_drive_file_text,
    get_submission_status,
    get_submission,
    list_students,
    read_word_file,
    read_excel_file,
    read_pptx_file,
]
