# ta/tools/__init__.py
from ta.tools.classroom import (
    create_assignment,
    create_material,
    get_submission,
    get_submission_status,
    list_assignments,
    list_courses,
    list_students,
    post_announcement,
)
from ta.tools.docs import add_doc_comment, get_doc_text
from ta.tools.drive import get_drive_file_text, upload_file_to_drive
from ta.tools.grading import (
    analyze_submission,
    batch_grade_assignment,
    load_rubric,
    post_grade,
    post_private_comment,
)

ALL_TOOLS = [
    # Classroom — read
    list_courses,
    list_students,
    list_assignments,
    get_submission_status,
    get_submission,
    # Classroom — write (confirmation required)
    post_announcement,
    create_assignment,
    create_material,
    # Grading
    load_rubric,
    analyze_submission,
    batch_grade_assignment,
    post_grade,
    post_private_comment,
    # Drive
    get_drive_file_text,
    upload_file_to_drive,
    # Docs
    get_doc_text,
    add_doc_comment,
]
