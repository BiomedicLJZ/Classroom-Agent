# ta/tools/__init__.py
from ta.tools.accounts import list_accounts, switch_account
from ta.tools.classroom import (
    create_assignment,
    create_material,
    delete_invitation,
    get_submission,
    get_submission_status,
    invite_user,
    list_assignments,
    list_courses,
    list_invitations,
    list_students,
    post_announcement,
)
from ta.tools.docs import add_doc_comment, get_doc_text
from ta.tools.drive import get_drive_file_text, upload_file_to_drive
from ta.tools.office import (
    append_excel_rows,
    append_to_word_file,
    get_excel_sheet_names,
    list_office_files,
    read_excel_file,
    read_pptx_file,
    read_word_file,
    write_excel_file,
    write_pptx_file,
    write_word_file,
)
from ta.tools.grading import (
    analyze_submission,
    batch_grade_assignment,
    load_rubric,
    post_grade,
    post_private_comment,
)

ALL_TOOLS = [
    # Account management
    list_accounts,
    switch_account,
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
    invite_user,
    delete_invitation,
    # Classroom — invitations (read)
    list_invitations,
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
    # Office — read
    read_word_file,
    read_excel_file,
    get_excel_sheet_names,
    read_pptx_file,
    list_office_files,
    # Office — write
    write_word_file,
    append_to_word_file,
    write_excel_file,
    append_excel_rows,
    write_pptx_file,
]
