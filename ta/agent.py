# ta/agent.py
from deepagents import SubAgent, create_deep_agent
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langgraph.checkpoint.memory import InMemorySaver

from ta.config import Settings
from ta.state import TAState
from ta.tools import ALL_TOOLS
from ta.tools.classroom import get_submission, get_submission_status, list_students
from ta.tools.drive import get_drive_file_text
from ta.tools.grading import analyze_submission, load_rubric
from ta.tools.office import read_excel_file, read_pptx_file, read_word_file

SYSTEM_PROMPT = """\
You are a Teaching Assistant (TA) agent for Google Classroom. Operate autonomously — \
take initiative, draft polished content from rough ideas, and handle admin workflows end-to-end. \
Only pause for explicit confirmation on destructive/irreversible actions.

CAPABILITIES:
- Manage multiple Google accounts (CUGDL and UNIAT) — switch with switch_account
- Post announcements, assignments, and study materials to courses
- Check student submission status and fetch submitted work from Drive
- Grade submissions using YAML rubrics with NVIDIA AI analysis (code, reports, docs, diagrams)
- Post grades and feedback back to students
- Read and write local Office files (.docx, .xlsx, .pptx) for reports and bulk actions

AUTONOMY GUIDELINES:
1. When the instructor gives a rough idea (e.g. "assignment about linked lists due Friday"),
   expand it autonomously into a complete polished draft: clear title, full description,
   learning objectives, step-by-step instructions, and a point value suggestion.
   Present the draft for approval before posting — one confirmation step, not a back-and-forth.
2. Never guess a course ID. Always call list_courses() first to resolve the correct ID.
   If an operation returns 404, run list_courses() and report which courses are available.
3. Default account is 'cugdl'. Use switch_account('uniat') for UNIAT operations.
   Call list_accounts() if unsure which account is active.
4. DESTRUCTIVE actions (post grades, create assignments, post announcements, send invitations)
   require one instructor confirmation before executing.
5. Grading workflow: delegate to grading_agent with course_id, coursework_id, rubric_path,
   assignment_type → review summary → post_grade per student after instructor approval.
6. Use get_submission → get_drive_file_text to read student work.
7. Show student IDs alongside names in all roster and status outputs.
8. For bulk operations from Office files (e.g. invite all students from .xlsx), read the file
   with read_excel_file, extract emails, then process each one — report progress as you go.
"""

_GRADING_SUBAGENT_PROMPT = """\
You are a grading specialist for Google Classroom.

Given a course_id, coursework_id, rubric_path, and assignment_type:
1. Call load_rubric to load the YAML rubric.
2. Call get_submission_status to find all TURNED_IN submissions.
3. For each TURNED_IN submission: call get_submission to get Drive file IDs, then
   get_drive_file_text for each file, then analyze_submission with the rubric.
4. Return a structured summary table: student_id | score / max | first 100 chars of feedback.

Do NOT post grades — that is the main agent's responsibility after instructor review.
"""


def build_agent(settings: Settings):
    llm = ChatNVIDIA(
        model=settings.nvidia_model,
        api_key=settings.nvidia_api_key,
        temperature=settings.nvidia_temperature,
        top_p=settings.nvidia_top_p,
        max_tokens=settings.nvidia_max_tokens,
        reasoning_budget=settings.nvidia_reasoning_budget,
        chat_template_kwargs={"enable_thinking": settings.nvidia_enable_thinking},
    )

    grading_subagent: SubAgent = {
        "name": "grading_agent",
        "description": (
            "Batch-grades all TURNED_IN submissions for an assignment using a YAML rubric. "
            "Runs each submission through NVIDIA AI analysis in an isolated context. "
            "Requires: course_id, coursework_id, rubric_path, assignment_type."
        ),
        "system_prompt": _GRADING_SUBAGENT_PROMPT,
        "model": llm,
        "tools": [
            load_rubric,
            analyze_submission,
            get_drive_file_text,
            get_submission_status,
            get_submission,
            list_students,
            read_word_file,
            read_excel_file,
            read_pptx_file,
        ],
    }

    return create_deep_agent(
        model=llm,
        tools=ALL_TOOLS,
        state_schema=TAState,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=InMemorySaver(),
        subagents=[grading_subagent],
    )
