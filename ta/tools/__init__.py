# ta/tools/__init__.py
from ta.tools.accounts import list_accounts, register_account, switch_account
from ta.tools.calendar import (
    create_calendar_event,
    get_weekly_briefing,
    list_calendar_events,
)
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
    list_course_ids,
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
from ta.tools.files import (
    list_files,
    read_notebook_file,
    read_text_file,
    write_notebook_file,
    write_text_file,
)
from ta.tools.grading import (
    analyze_submission,
    batch_grade_assignment,
    export_grades,
    import_grades,
    load_rubric,
    post_grade,
)
from ta.tools.memory import summarize_history
from ta.tools.office import (
    append_excel_rows,
    append_to_word_file,
    export_to_pdf,
    get_excel_sheet_names,
    list_office_files,
    read_excel_file,
    read_pptx_file,
    read_word_file,
    write_excel_file,
    write_pptx_file,
    write_word_file,
)
from ta.tools.planning import load_syllabus, save_syllabus
from ta.tools.workspace import (
    get_workspace_resource_path,
    list_workspace_contents,
    setup_course_workspace,
)

ALL_TOOLS = [
    # Account management
    list_accounts,
    switch_account,
    register_account,
    # Classroom — read
    list_course_ids,
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
    import_grades,
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
    export_to_pdf,
    # Files
    write_text_file,
    read_text_file,
    write_notebook_file,
    read_notebook_file,
    list_files,
    # Workspace
    setup_course_workspace,
    get_workspace_resource_path,
    list_workspace_contents,
    # Planning
    save_syllabus,
    load_syllabus,
    # Calendar
    list_calendar_events,
    create_calendar_event,
    get_weekly_briefing,
    # Memory
    summarize_history,
]
