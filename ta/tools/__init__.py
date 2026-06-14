# ta/tools/__init__.py
from ta.tools.accounts import list_accounts, switch_account
from ta.tools.classroom import (
    create_assignment,
    create_material,
    create_topic,
    delete_announcement,
    delete_assignment,
    delete_invitation,
    delete_material,
    get_submission,
    get_submission_status,
    invite_user,
    list_announcements,
    list_assignments,
    list_courses,
    list_invitations,
    list_materials,
    list_students,
    list_topics,
    post_announcement,
    update_announcement,
    update_assignment,
    update_material,
)
from ta.tools.docs import add_doc_comment, get_doc_text
from ta.tools.drive import get_drive_file_text, upload_file_to_drive
from ta.tools.grading import (
    analyze_submission,
    batch_grade_assignment,
    export_grades,
    load_rubric,
    post_grade,
)
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
    # Classroom — admin (rework)
    update_assignment,
    delete_assignment,
    list_announcements,
    update_announcement,
    delete_announcement,
    list_materials,
    update_material,
    delete_material,
    list_topics,
    create_topic,
    # Classroom — invitations (read)
    list_invitations,
    # Grading
    load_rubric,
    analyze_submission,
    batch_grade_assignment,
    post_grade,
    export_grades,
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
